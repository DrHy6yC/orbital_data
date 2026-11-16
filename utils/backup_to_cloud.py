"""Резервное копирование в облако в пределах бесплатного уровня.

Копирует:
1. объекты бакета bronze из локального S3 (RustFS или MinIO) в облачный бакет,
   в папку bronze/. Копируются только новые объекты: в облаке ничего не
   перезаписывается и не удаляется;
2. дамп PostgreSQL (pg_dump, сжатый gzip) в папку postgres/. Хранятся последние
   N дампов, более старые удаляются.

Слои Silver и Gold не копируются: их можно пересобрать из Bronze.

Защита от платных расходов: перед каждой загрузкой проверяется, что общий размер
облачного бакета не превысит BACKUP_MAX_MB. Если превысит, копирование
останавливается.

Настройки в .env:
    BACKUP_S3_ENDPOINT, BACKUP_S3_REGION, BACKUP_S3_BUCKET,
    BACKUP_S3_ACCESS_KEY, BACKUP_S3_SECRET_KEY   облачный бакет
    BACKUP_SOURCE        имя локального хранилища (по умолчанию RUSTFS),
                         читаются S3_<ИМЯ>_HOST, _PORT, _ACCESS_KEY, _SECRET_KEY
    BACKUP_MAX_MB        лимит размера бакета в МиБ (по умолчанию 800)
    BACKUP_KEEP_DUMPS    сколько дампов хранить (по умолчанию 7)
    POSTGRES_USER, POSTGRES_DB   для дампа (контейнер postgres должен работать)

Запуск из корня проекта:
    uv run --env-file .env python utils/backup_to_cloud.py --check
    uv run --env-file .env python utils/backup_to_cloud.py --dry-run
    uv run --env-file .env python utils/backup_to_cloud.py
"""

import argparse
import gzip
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIB = 1024 * 1024
SOURCE_BUCKET = "bronze"
CLOUD_BRONZE_PREFIX = "bronze/"
CLOUD_POSTGRES_PREFIX = "postgres/"
SKIP_PREFIX = "_healthcheck/"  # служебные объекты проверки, их не копируем
# Объекты до 64 МиБ загружаются одним запросом (меньше операций PUT).
UPLOAD_CONFIG = TransferConfig(multipart_threshold=64 * MIB, multipart_chunksize=64 * MIB)

# Счётчики операций за запуск (для контроля бесплатного лимита).
stats = {"put": 0, "list": 0, "bytes": 0}


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"Не задана переменная {name}. Добавь её в .env и запускай через uv run --env-file .env")
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


def list_objects(client, bucket: str, prefix: str = "", cloud: bool = False) -> dict[str, int]:
    """Возвращает {ключ: размер}. Для облака считает запросы LIST."""
    objects = {}
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
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


def backup_bronze(local, cloud, settings: dict, cloud_all: dict, total: int, dry_run: bool):
    """Копирует новые объекты bronze. Возвращает (новый размер бакета, успех)."""
    local_objects = {
        key: size
        for key, size in list_objects(local, SOURCE_BUCKET).items()
        if not key.startswith(SKIP_PREFIX)
    }
    in_cloud = {
        key[len(CLOUD_BRONZE_PREFIX):]: size
        for key, size in cloud_all.items()
        if key.startswith(CLOUD_BRONZE_PREFIX)
    }
    for key, size in local_objects.items():
        if key in in_cloud and in_cloud[key] != size:
            print(f"[ПРЕДУПРЕЖДЕНИЕ] {key}: размер в облаке отличается, не перезаписываю")
    todo = [(key, size) for key, size in sorted(local_objects.items()) if key not in in_cloud]
    todo_size = sum(size for _, size in todo)
    print(
        f"Bronze: объектов локально {len(local_objects)}, "
        f"к копированию {len(todo)} ({todo_size / MIB:.2f} МиБ)"
    )
    for key, size in todo:
        if total + size > settings["max_bytes"]:
            print(f"[СТОП] {key}: бакет превысил бы лимит {settings['max_bytes'] // MIB} МиБ")
            return total, False
        if dry_run:
            print(f"[ПРОБНЫЙ ЗАПУСК] {key} ({size} байт)")
        else:
            body = local.get_object(Bucket=SOURCE_BUCKET, Key=key)["Body"]
            cloud.upload_fileobj(body, settings["bucket"], CLOUD_BRONZE_PREFIX + key, Config=UPLOAD_CONFIG)
            stats["put"] += 1
            stats["bytes"] += size
            print(f"[OK] {key}")
        total += size
    return total, True


def backup_postgres(cloud, settings: dict, cloud_all: dict, total: int, dry_run: bool):
    """Делает дамп PostgreSQL и загружает его. Возвращает (новый размер бакета, успех)."""
    user = required("POSTGRES_USER")
    db = required("POSTGRES_DB")
    command = ["docker", "compose", "exec", "-T", "postgres", "pg_dump", "-U", user, "-d", db]
    try:
        result = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True)
    except FileNotFoundError:
        print("[ОШИБКА] команда docker не найдена")
        return total, False
    if result.returncode != 0 or not result.stdout:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        print(f"[ОШИБКА] pg_dump не выполнен (контейнер postgres запущен?): {message}")
        return total, False

    data = gzip.compress(result.stdout)  # дамп небольшой, держим в памяти
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = f"{CLOUD_POSTGRES_PREFIX}{db}_{stamp}.sql.gz"
    if total + len(data) > settings["max_bytes"]:
        print(f"[СТОП] дамп ({len(data) / MIB:.2f} МиБ) превысил бы лимит бакета")
        return total, False
    if dry_run:
        print(f"[ПРОБНЫЙ ЗАПУСК] {key} ({len(data)} байт)")
    else:
        cloud.put_object(Bucket=settings["bucket"], Key=key, Body=data)
        stats["put"] += 1
        stats["bytes"] += len(data)
        print(f"[OK] {key} ({len(data)} байт)")
    total += len(data)

    # Храним только последние N дампов. Удаляем только внутри папки postgres/.
    dumps = sorted(k for k in cloud_all if k.startswith(CLOUD_POSTGRES_PREFIX)) + [key]
    for old_key in dumps[: max(0, len(dumps) - settings["keep_dumps"])]:
        if dry_run:
            print(f"[ПРОБНЫЙ ЗАПУСК] удалил бы старый дамп {old_key}")
        else:
            cloud.delete_object(Bucket=settings["bucket"], Key=old_key)
            print(f"[OK] удалён старый дамп {old_key}")
    return total, True


def main() -> None:
    parser = argparse.ArgumentParser(description="Резервное копирование в облако")
    parser.add_argument("--check", action="store_true", help="только проверить доступ к облачному бакету")
    parser.add_argument("--dry-run", action="store_true", help="показать, что будет скопировано, ничего не загружая")
    parser.add_argument("--only", choices=("bronze", "postgres"), help="копировать только одну часть")
    args = parser.parse_args()

    settings = load_settings()
    cloud = make_client(
        settings["endpoint"], settings["region"], settings["access_key"], settings["secret_key"]
    )
    ok = True
    try:
        if args.check:
            check_access(cloud, settings["bucket"])
        else:
            cloud_all = list_objects(cloud, settings["bucket"], cloud=True)
            total = sum(cloud_all.values())
            print(f"Облачный бакет: {total / MIB:.2f} МиБ из {settings['max_bytes'] // MIB} МиБ")
            if args.only in (None, "bronze"):
                local = make_local_client(settings["source"])
                total, done = backup_bronze(local, cloud, settings, cloud_all, total, args.dry_run)
                ok = ok and done
            if args.only in (None, "postgres"):
                total, done = backup_postgres(cloud, settings, cloud_all, total, args.dry_run)
                ok = ok and done
            print(f"Размер бакета после копирования: {total / MIB:.2f} МиБ")
    except (ClientError, BotoCoreError) as error:
        sys.exit(f"[ОШИБКА] {error}")

    operations = stats["put"] + stats["list"]
    print(
        f"За запуск: загружено {stats['bytes'] / MIB:.2f} МиБ, операций записи и листинга "
        f"{operations} (бесплатно 10 000 в месяц)"
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
