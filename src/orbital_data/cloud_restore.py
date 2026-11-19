"""Восстановление снимков Bronze из облака в основное хранилище.

Модуль отвечает за имена ключей и за одну операцию восстановления:
скачать объект бэкапа, распаковать gzip, сверить sha256 с метаданными
объекта и с записью в базе, загрузить файл в RustFS. Разбор
аргументов и печать плана остаются в utils/restore_from_cloud.py.
"""

import gzip
import hashlib
import shutil
from datetime import datetime
from pathlib import Path

from botocore.client import BaseClient

from orbital_data.backup_retention import (
    CLOUD_BRONZE_PREFIX,
    GZIP_SUFFIX,
    parse_key,
)
from orbital_data.cloud_objects import (
    download_object,
    format_size,
    stored_checksum,
)
from orbital_data.mirror import ensure_bucket, read_object_size

BRONZE_BUCKET = "bronze"


def parse_dataset(value: str) -> str:
    """Проверяет формат «источник/набор» и возвращает значение."""
    source, separator, dataset = value.strip().partition("/")
    if not source or not separator or not dataset or "/" in dataset:
        raise ValueError(f"нужен формат источник/набор, получено: {value}")
    return f"{source}/{dataset}"


def dataset_of(cloud_key: str) -> str | None:
    """Возвращает «источник/набор» из ключа объекта облака."""
    parts = cloud_key.removeprefix(CLOUD_BRONZE_PREFIX).split("/")
    if len(parts) != 3:
        return None
    return f"{parts[0]}/{parts[1]}"


def newest_keys(cloud_keys: list[str], dataset: str | None) -> list[str]:
    """Оставляет последний снимок каждого набора."""
    prefix = CLOUD_BRONZE_PREFIX
    if dataset:
        prefix = f"{CLOUD_BRONZE_PREFIX}{dataset}/"
    newest: dict[str, tuple[datetime, str]] = {}
    for cloud_key in cloud_keys:
        if not cloud_key.startswith(prefix):
            continue
        parsed = parse_key(cloud_key)
        name = dataset_of(cloud_key)
        if parsed is None or name is None:
            continue
        moment = parsed[1]
        if name not in newest or moment > newest[name][0]:
            newest[name] = (moment, cloud_key)
    return [newest[name][1] for name in sorted(newest)]


def rustfs_key(cloud_key: str) -> str:
    """Убирает из ключа облака префикс bronze/ и суффикс .gz."""
    key = cloud_key.removeprefix(CLOUD_BRONZE_PREFIX)
    if key.endswith(GZIP_SUFFIX):
        key = key[: -len(GZIP_SUFFIX)]
    return key


def restore_object(
    cloud: BaseClient,
    storage: BaseClient,
    bucket: str,
    cloud_key: str,
    temp_directory: Path,
    checksums: dict[str, str],
) -> int | None:
    """Проверяет объект облака и загружает его в RustFS.

    Возвращает размер распакованного файла или None при ошибке.
    """
    key = rustfs_key(cloud_key)
    stored = stored_checksum(
        cloud.head_object(Bucket=bucket, Key=cloud_key).get("Metadata", {})
    )
    archive_path = temp_directory / "restore_object.gz"
    unpacked_path = temp_directory / "restore_object"
    packed = download_object(cloud, bucket, cloud_key, archive_path)
    with gzip.open(archive_path, "rb") as source:
        with unpacked_path.open("wb") as target:
            shutil.copyfileobj(source, target)
    with unpacked_path.open("rb") as file:
        actual = hashlib.file_digest(file, "sha256").hexdigest()
    size = unpacked_path.stat().st_size
    print(cloud_key)
    print(f"  сжато {format_size(packed)}, распаковано {format_size(size)}")

    if not stored:
        print("  [ВНИМАНИЕ] sha256 в метаданных нет, проверена распаковка")
    elif stored != actual:
        print(
            f"  [ОШИБКА] sha256 не совпал: метаданные {stored}, файл {actual}"
        )
        return None
    else:
        print("  [OK] sha256 совпал с метаданными")

    expected = checksums.get(key)
    if not expected:
        print("  [ВНИМАНИЕ] снимка нет в snapshots, сверка с базой пропущена")
    elif expected != actual:
        print(f"  [ОШИБКА] sha256 не совпал с базой: {expected}")
        return None
    else:
        print("  [OK] sha256 совпал с базой")

    if read_object_size(storage, bucket, key) == size:
        print(f"  уже на месте: {BRONZE_BUCKET}/{key}")
        return size

    ensure_bucket(storage, bucket)
    with unpacked_path.open("rb") as body:
        storage.upload_fileobj(body, bucket, key)
    copied = read_object_size(storage, bucket, key)
    if copied != size:
        print(f"  [ОШИБКА] после загрузки размер {copied}, ожидался {size}")
        return None
    print(f"  восстановлен: {BRONZE_BUCKET}/{key}")
    return size
