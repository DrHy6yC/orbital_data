"""Проверка того, что резервная копия из облака восстанавливается.

Скачивает объекты бэкапа, распаковывает gzip и сверяет sha256
с метаданными, записанными при загрузке. Для снимков Bronze
дополнительно сверяется локальный оригинал из data/, если он есть.

По умолчанию проверяются последние снимки всех наборов в bronze/
и последний дамп в postgres/. Ключ --key проверяет один объект,
ключ --all — весь бэкап целиком (скачивается всё, это долго).

Запуск из корня проекта:
    uv run --env-file .env python utils/check_backup_restore.py
    uv run --env-file .env python utils/check_backup_restore.py --key <ключ>

В облаке ничего не меняется: только LIST, HEAD и GET.
Настройки в .env: BACKUP_S3_ENDPOINT, BACKUP_S3_REGION,
BACKUP_S3_BUCKET, BACKUP_S3_ACCESS_KEY, BACKUP_S3_SECRET_KEY.
"""

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from orbital_data.backup_retention import (  # noqa: E402
    CLOUD_BRONZE_PREFIX,
    GZIP_SUFFIX,
)
from orbital_data.cloud_objects import (  # noqa: E402
    CLOUD_POSTGRES_PREFIX,
    download_object,
    format_size,
    latest_by_dataset,
    list_cloud_keys,
    make_cloud_client,
    read_required_env,
    stored_checksum,
    unpacked_sha256,
)

DATA_DIRECTORY = PROJECT_ROOT / "data"


def latest_dump(keys: list[str]) -> str | None:
    """Возвращает последний дамп PostgreSQL по имени объекта."""
    dumps = [key for key in keys if key.startswith(CLOUD_POSTGRES_PREFIX)]
    return max(dumps) if dumps else None


def local_path_for(key: str) -> Path | None:
    """Возвращает путь к оригиналу снимка в каталоге data/."""
    if not key.startswith(CLOUD_BRONZE_PREFIX):
        return None
    relative = key.removeprefix(CLOUD_BRONZE_PREFIX)
    if relative.endswith(GZIP_SUFFIX):
        relative = relative[: -len(GZIP_SUFFIX)]
    return DATA_DIRECTORY / relative


def local_sha256(file_path: Path) -> str:
    """Считает sha256 локального файла."""
    with file_path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def check_object(
    client: BaseClient,
    bucket: str,
    key: str,
    temp_directory: str,
) -> bool:
    """Проверяет скачивание, распаковку и sha256 одного объекта."""
    archive_path = Path(temp_directory) / "backup_object.gz"
    head = client.head_object(Bucket=bucket, Key=key)
    stored = stored_checksum(head.get("Metadata", {}))
    packed = download_object(client, bucket, key, archive_path)
    actual, unpacked = unpacked_sha256(archive_path)
    print(key)
    print(
        f"  сжато {format_size(packed)}, распаковано {format_size(unpacked)}"
    )

    ok = True
    if not stored:
        print("  [ВНИМАНИЕ] sha256 в метаданных нет, проверена распаковка")
    elif stored == actual:
        print(f"  [OK] sha256 совпал с метаданными: {actual}")
    else:
        print(
            f"  [ОШИБКА] sha256 не совпал: метаданные {stored}, файл {actual}"
        )
        ok = False

    local = local_path_for(key)
    if local is not None and local.is_file():
        if local_sha256(local) == actual:
            print(f"  [OK] совпал с оригиналом {local}")
        else:
            print(f"  [ОШИБКА] оригинал отличается: {local}")
            ok = False
    return ok


def choose_keys(
    keys: list[str], check_all: bool, one_key: str | None
) -> list[str]:
    """Выбирает объекты для проверки по ключам запуска."""
    if one_key:
        if one_key not in keys:
            sys.exit(f"В бакете нет объекта {one_key}")
        return [one_key]
    if check_all:
        return sorted(
            key
            for key in keys
            if key.startswith(CLOUD_BRONZE_PREFIX)
            or key.startswith(CLOUD_POSTGRES_PREFIX)
        )
    selected = latest_by_dataset(keys)
    dump = latest_dump(keys)
    if dump:
        selected.append(dump)
    return selected


def main() -> None:
    """Проверяет восстановление объектов бэкапа из облака."""
    parser = argparse.ArgumentParser(
        description="Проверка восстановления резервной копии из облака",
    )
    parser.add_argument(
        "--key",
        help="проверить один объект по его ключу в бакете",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="проверить все объекты бэкапа, а не только последние",
    )
    args = parser.parse_args()

    bucket = read_required_env("BACKUP_S3_BUCKET")
    client = make_cloud_client()
    try:
        keys = list_cloud_keys(client, bucket)
    except (ClientError, BotoCoreError) as error:
        sys.exit(f"[ОШИБКА] не удалось прочитать бакет: {error}")

    selected = choose_keys(keys, args.all, args.key)
    if not selected:
        sys.exit("В бакете нет объектов бэкапа")

    print(f"Объектов к проверке: {len(selected)}")
    ok = True
    with tempfile.TemporaryDirectory() as temp_directory:
        for key in selected:
            try:
                done = check_object(client, bucket, key, temp_directory)
            except (ClientError, BotoCoreError, OSError) as error:
                print(f"{key}\n  [ОШИБКА] {error}")
                done = False
            ok = ok and done

    message = "ИТОГ: бэкап восстанавливается"
    print(message if ok else "ИТОГ: есть ошибки")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
