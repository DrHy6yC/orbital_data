"""Резервное копирование в облако в пределах бесплатного уровня.

Копирует:
1. объекты бакета bronze из локального S3 (RustFS или MinIO) в облачный
   бакет, в папку bronze/, сжатыми gzip. Копируются только отсутствующие
   ключи; sha256 пишется в метаданные объекта;
2. дамп PostgreSQL (pg_dump, сжатый gzip) в папку postgres/. Хранятся
   последние N дампов, более старые удаляются.

Просроченные объекты bronze удаляются по окнам хранения
BACKUP_KEEP_<НАБОР>_DAYS и только после успешной загрузки новых.

Слои Silver и Gold не копируются: их можно пересобрать из Bronze.

Защита от платных расходов: перед каждой загрузкой проверяется, что общий размер
облачного бакета не превысит BACKUP_MAX_MB. Если превысит, копирование
останавливается.

Настройки в .env:
    BACKUP_S3_ENDPOINT, BACKUP_S3_REGION, BACKUP_S3_BUCKET,
    BACKUP_S3_ACCESS_KEY, BACKUP_S3_SECRET_KEY   облачный бакет
    BACKUP_SOURCE        имя локального хранилища (по умолчанию RUSTFS),
                         читаются S3_<ИМЯ>_HOST, _PORT, _ACCESS_KEY, _SECRET_KEY
    BACKUP_MAX_MB        лимит размера бакета в МБ (по умолчанию 800)
    BACKUP_KEEP_DUMPS    сколько дампов хранить (по умолчанию 7)
    POSTGRES_USER, POSTGRES_DB   для дампа (контейнер postgres должен работать)

Запуск из корня проекта:
    uv run --env-file .env python utils/backup_to_cloud.py --check
    uv run --env-file .env python utils/backup_to_cloud.py --dry-run
    uv run --env-file .env python utils/backup_to_cloud.py
"""

import argparse
import gzip
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from orbital_data.backup_retention import (  # noqa: E402
    RetentionPlan,
    expired_keys,
)

MIB = 1024 * 1024
SOURCE_BUCKET = "bronze"
CLOUD_BRONZE_PREFIX = "bronze/"
CLOUD_POSTGRES_PREFIX = "postgres/"
SKIP_PREFIX = "_healthcheck/"  # служебные объекты проверки, их не копируем
# Объекты до 64 МБ загружаются одним запросом (меньше операций PUT).
UPLOAD_CONFIG = TransferConfig(
    multipart_threshold=64 * MIB, multipart_chunksize=64 * MIB
)
GZIP_SUFFIX = ".gz"
COMPRESS_LEVEL = 9
CHUNK_SIZE = 1024 * 1024

RETENTION_PREFIX = "BACKUP_KEEP_"
RETENTION_SUFFIX = "_DAYS"

# Счётчики операций за запуск (для контроля бесплатного лимита).
stats = {"put": 0, "list": 0, "delete": 0, "bytes": 0}


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(
            f"Не задана переменная {name}. Добавь её в .env и запускай через uv run --env-file .env"
        )
    return value


def number(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip() or str(default)
    if not raw.isdigit():
        sys.exit(f"{name} должен быть целым числом, сейчас: {raw}")
    return int(raw)


def load_settings() -> dict:
    return {
        "endpoint": required("BACKUP_S3_ENDPOINT"),
        "region": required("BACKUP_S3_REGION"),
        "bucket": required("BACKUP_S3_BUCKET"),
        "access_key": required("BACKUP_S3_ACCESS_KEY"),
        "secret_key": required("BACKUP_S3_SECRET_KEY"),
        "source": os.environ.get("BACKUP_SOURCE", "RUSTFS").strip().upper(),
        "max_bytes": number("BACKUP_MAX_MB", 800) * MIB,
        "keep_dumps": max(1, number("BACKUP_KEEP_DUMPS", 7)),
    }


def make_client(endpoint: str, region: str, access_key: str, secret_key: str):
    config = Config(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        retries={"max_attempts": 3, "mode": "standard"},
        connect_timeout=10,
        read_timeout=120,
        # Новые boto3 добавляют контрольные суммы, которые не все хранилища принимают.
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=config,
    )


def make_local_client(source: str):
    prefix = f"S3_{source}_"
    host = required(prefix + "HOST")
    port = required(prefix + "PORT")
    return make_client(
        f"http://{host}:{port}",
        "us-east-1",
        required(prefix + "ACCESS_KEY"),
        required(prefix + "SECRET_KEY"),
    )


def list_objects(
    client, bucket: str, prefix: str = "", cloud: bool = False
) -> dict[str, int]:
    """Возвращает {ключ: размер}. Для облака считает запросы LIST."""
    objects = {}
    for page in client.get_paginator("list_objects_v2").paginate(
        Bucket=bucket, Prefix=prefix
    ):
        if cloud:
            stats["list"] += 1
        for item in page.get("Contents", []):
            objects[item["Key"]] = item["Size"]
    return objects


def check_access(cloud, bucket: str) -> None:
    """Проверяет доступ к облачному бакету: запись, чтение и удаление маленького объекта."""
    cloud.head_bucket(Bucket=bucket)
    key = f"_healthcheck/{uuid.uuid4().hex}.txt"
    body = b"orbital-data backup check"
    cloud.put_object(Bucket=bucket, Key=key, Body=body)
    stats["put"] += 1
    received = cloud.get_object(Bucket=bucket, Key=key)["Body"].read()
    cloud.delete_object(Bucket=bucket, Key=key)
    if received != body:
        sys.exit("[ОШИБКА] прочитанные данные отличаются от записанных")
    print(f"[OK] доступ к бакету {bucket}: запись, чтение, удаление")


def download_object(local: BaseClient, key: str, target_path: Path) -> str:
    """Скачивает объект в файл и возвращает его sha256."""
    digest = hashlib.sha256()
    with local.get_object(Bucket=SOURCE_BUCKET, Key=key)["Body"] as body:
        with target_path.open("wb") as file:
            chunk = body.read(CHUNK_SIZE)
            while chunk:
                digest.update(chunk)
                file.write(chunk)
                chunk = body.read(CHUNK_SIZE)
    return digest.hexdigest()


def compress_file(source_path: Path, target_path: Path) -> int:
    """Сжимает файл gzip и возвращает размер результата."""
    with source_path.open("rb") as source:
        with gzip.open(
            target_path, "wb", compresslevel=COMPRESS_LEVEL
        ) as target:
            shutil.copyfileobj(source, target)
    return target_path.stat().st_size


def read_retention() -> dict[str, int]:
    """Читает окна хранения наборов из BACKUP_KEEP_<НАБОР>_DAYS."""
    retention = {}
    for name, raw in os.environ.items():
        if not name.startswith(RETENTION_PREFIX):
            continue
        if not name.endswith(RETENTION_SUFFIX):
            continue
        dataset = name[len(RETENTION_PREFIX) : -len(RETENTION_SUFFIX)]
        dataset = dataset.lower()
        value = raw.strip()
        if not value:
            continue
        if not value.isdigit() or int(value) == 0:
            sys.exit(
                f"{name} должен быть целым числом дней больше нуля, "
                f"сейчас: {value}"
            )
        retention[dataset] = int(value)
    return retention


def show_plan(
    plan: RetentionPlan,
    cloud_all: dict[str, int],
    is_dry_run: bool,
) -> None:
    """Печатает, что будет удалено по истечении окон хранения."""
    freed = sum(cloud_all[key] for key in plan.expired)
    print(
        f"Просрочено по окнам хранения: {len(plan.expired)} объектов, "
        f"{freed / MIB:.2f} МБ"
    )
    if is_dry_run:
        for key in plan.expired:
            print(f"[ПРОБНЫЙ ЗАПУСК] удалил бы {key}")
    for key in plan.unknown:
        print(f"[ВНИМАНИЕ] {key}: окно не задано, объект остаётся")


def delete_expired(cloud: BaseClient, bucket: str, expired: list[str]) -> bool:
    """Удаляет просроченные объекты. Возвращает признак успеха."""
    ok = True
    for key in expired:
        try:
            cloud.delete_object(Bucket=bucket, Key=key)
        except (ClientError, BotoCoreError) as error:
            print(f"[ОШИБКА] не удалён {key}: {error}")
            ok = False
            continue
        stats["delete"] += 1
        print(f"[OK] удалён {key}")
    return ok


def backup_bronze(
    local: BaseClient,
    cloud: BaseClient,
    settings: dict,
    cloud_all: dict[str, int],
    expired: set[str],
    total: int,
    is_dry_run: bool,
) -> tuple[int, bool]:
    """Копирует отсутствующие объекты bronze в gzip.

    Просроченные объекты не загружаются заново: их удалит этот же
    запуск. Возвращает новый размер бакета и признак успеха.
    """
    local_objects = {
        key: size
        for key, size in list_objects(local, SOURCE_BUCKET).items()
        if not key.startswith(SKIP_PREFIX)
    }
    todo = []
    for key, size in sorted(local_objects.items()):
        cloud_key = CLOUD_BRONZE_PREFIX + key + GZIP_SUFFIX
        if cloud_key in cloud_all or cloud_key in expired:
            continue
        todo.append((key, size))
    print(
        f"Bronze: объектов локально {len(local_objects)}, "
        f"к копированию {len(todo)}"
    )
    with tempfile.TemporaryDirectory() as temp_directory:
        for key, size in todo:
            if is_dry_run:
                print(f"[ПРОБНЫЙ ЗАПУСК] {key} ({size} байт)")
                continue
            downloaded = Path(temp_directory) / "snapshot"
            packed = Path(temp_directory) / "snapshot.gz"
            try:
                checksum = download_object(local, key, downloaded)
                packed_size = compress_file(downloaded, packed)
            except (ClientError, BotoCoreError, OSError) as error:
                print(f"[ОШИБКА] {key}: {error}")
                return total, False
            if total + packed_size > settings["max_bytes"]:
                print(
                    f"[СТОП] {key}: бакет превысил бы лимит "
                    f"{settings['max_bytes'] // MIB} МБ"
                )
                return total, False
            cloud_key = CLOUD_BRONZE_PREFIX + key + GZIP_SUFFIX
            try:
                cloud.upload_file(
                    Filename=str(packed),
                    Bucket=settings["bucket"],
                    Key=cloud_key,
                    ExtraArgs={"Metadata": {"sha256": checksum}},
                    Config=UPLOAD_CONFIG,
                )
            except (ClientError, BotoCoreError) as error:
                print(f"[ОШИБКА] {key}: {error}")
                return total, False
            stats["put"] += 1
            stats["bytes"] += packed_size
            total += packed_size
            print(
                f"[OK] {key} -> {cloud_key} "
                f"({size / MIB:.2f} МБ -> {packed_size / MIB:.2f} МБ)"
            )
    return total, True


def backup_postgres(
    cloud, settings: dict, cloud_all: dict, total: int, dry_run: bool
):
    """Делает дамп PostgreSQL и загружает его. Возвращает (новый размер бакета, успех)."""
    user = required("POSTGRES_USER")
    db = required("POSTGRES_DB")
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "postgres",
        "pg_dump",
        "-U",
        user,
        "-d",
        db,
    ]
    try:
        result = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True)
    except FileNotFoundError:
        print("[ОШИБКА] команда docker не найдена")
        return total, False
    if result.returncode != 0 or not result.stdout:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        print(
            f"[ОШИБКА] pg_dump не выполнен (контейнер postgres запущен?): {message}"
        )
        return total, False

    checksum = hashlib.sha256(result.stdout).hexdigest()
    data = gzip.compress(result.stdout)  # дамп небольшой, держим в памяти
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    key = f"{CLOUD_POSTGRES_PREFIX}{db}_{stamp}.sql.gz"
    if total + len(data) > settings["max_bytes"]:
        print(
            f"[СТОП] дамп ({len(data) / MIB:.2f} МБ) превысил бы лимит бакета"
        )
        return total, False
    if dry_run:
        print(f"[ПРОБНЫЙ ЗАПУСК] {key} ({len(data)} байт)")
    else:
        cloud.put_object(
            Bucket=settings["bucket"],
            Key=key,
            Body=data,
            Metadata={"sha256": checksum},
        )
        stats["put"] += 1
        stats["bytes"] += len(data)
        print(f"[OK] {key} ({len(data)} байт)")
    total += len(data)

    # Храним только последние N дампов. Удаляем только внутри папки postgres/.
    dumps = sorted(
        k for k in cloud_all if k.startswith(CLOUD_POSTGRES_PREFIX)
    ) + [key]
    for old_key in dumps[: max(0, len(dumps) - settings["keep_dumps"])]:
        if dry_run:
            print(f"[ПРОБНЫЙ ЗАПУСК] удалил бы старый дамп {old_key}")
        else:
            cloud.delete_object(Bucket=settings["bucket"], Key=old_key)
            print(f"[OK] удалён старый дамп {old_key}")
    return total, True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Резервное копирование в облако"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="только проверить доступ к облачному бакету",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="показать, что будет скопировано, ничего не загружая",
    )
    parser.add_argument(
        "--only",
        choices=("bronze", "postgres"),
        help="копировать только одну часть",
    )
    args = parser.parse_args()

    settings = load_settings()
    cloud = make_client(
        settings["endpoint"],
        settings["region"],
        settings["access_key"],
        settings["secret_key"],
    )
    ok = True
    try:
        if args.check:
            check_access(cloud, settings["bucket"])
        else:
            cloud_all = list_objects(cloud, settings["bucket"], cloud=True)
            total = sum(cloud_all.values())
            print(
                f"Облачный бакет: {total / MIB:.2f} МБ "
                f"из {settings['max_bytes'] // MIB} МБ"
            )
            if args.only in (None, "bronze"):
                plan = expired_keys(
                    cloud_all, read_retention(), datetime.now(UTC)
                )
                show_plan(plan, cloud_all, args.dry_run)
                freed = sum(cloud_all[key] for key in plan.expired)
                local = make_local_client(settings["source"])
                total, done = backup_bronze(
                    local,
                    cloud,
                    settings,
                    cloud_all,
                    set(plan.expired),
                    total - freed,
                    args.dry_run,
                )
                ok = ok and done
                if not args.dry_run:
                    if not done:
                        print(
                            "Удаление пропущено: загрузка завершилась "
                            "с ошибкой"
                        )
                    elif plan.expired:
                        delete_expired(cloud, settings["bucket"], plan.expired)
            if args.only in (None, "postgres"):
                total, done = backup_postgres(
                    cloud, settings, cloud_all, total, args.dry_run
                )
                ok = ok and done
            if not args.dry_run:
                listed = list_objects(cloud, settings["bucket"], cloud=True)
                total = sum(listed.values())
            print(f"Размер бакета после копирования: {total / MIB:.2f} МБ")
    except (ClientError, BotoCoreError) as error:
        sys.exit(f"[ОШИБКА] {error}")

    operations = stats["put"] + stats["list"] + stats["delete"]
    print(
        f"За запуск: загружено {stats['bytes'] / MIB:.2f} МБ, "
        f"операций записи, удаления и листинга {operations} "
        f"(бесплатно 10 000 в месяц)"
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
