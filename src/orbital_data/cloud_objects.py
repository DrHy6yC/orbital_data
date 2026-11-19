"""Общие операции с облачным бакетом резервных копий.

Модуль знает только про S3-объекты: создаёт клиент по переменным
BACKUP_S3_*, перечисляет ключи, скачивает объекты, распаковывает
gzip и читает sha256 из метаданных. Что именно копировать и куда,
решают скрипты в utils/.
"""

import gzip
import hashlib
import os
import sys
from pathlib import Path

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.client import BaseClient
from botocore.config import Config

from orbital_data.backup_retention import parse_key

CLOUD_POSTGRES_PREFIX = "postgres/"
MIB = 1024 * 1024
CHUNK_SIZE = 1024 * 1024
# Объекты до 64 МБ скачиваются одним запросом, а не частями.
DOWNLOAD_CONFIG = TransferConfig(multipart_threshold=64 * MIB)


def read_required_env(name: str) -> str:
    """Возвращает значение переменной окружения или завершает работу."""
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"Не задана переменная {name}, проверьте .env")
    return value


def make_cloud_client() -> BaseClient:
    """Создаёт клиент облачного бакета по переменным BACKUP_S3_*."""
    config = Config(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        retries={"max_attempts": 3, "mode": "standard"},
        connect_timeout=10,
        read_timeout=120,
        # Новые boto3 добавляют контрольные суммы, которые не все
        # хранилища принимают.
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    )
    return boto3.client(
        "s3",
        endpoint_url=read_required_env("BACKUP_S3_ENDPOINT"),
        region_name=read_required_env("BACKUP_S3_REGION"),
        aws_access_key_id=read_required_env("BACKUP_S3_ACCESS_KEY"),
        aws_secret_access_key=read_required_env("BACKUP_S3_SECRET_KEY"),
        config=config,
    )


def list_cloud_keys(client: BaseClient, bucket: str) -> list[str]:
    """Возвращает ключи всех объектов бакета."""
    keys = []
    for page in client.get_paginator("list_objects_v2").paginate(
        Bucket=bucket
    ):
        for item in page.get("Contents", []):
            keys.append(item["Key"])
    return keys


def latest_by_dataset(keys: list[str]) -> list[str]:
    """Оставляет последний по времени снимок каждого набора."""
    latest = {}
    for key in keys:
        parsed = parse_key(key)
        if parsed is None:
            continue
        dataset, moment = parsed
        if dataset not in latest or moment > latest[dataset][0]:
            latest[dataset] = (moment, key)
    return [latest[dataset][1] for dataset in sorted(latest)]


def download_object(
    client: BaseClient, bucket: str, key: str, target_path: Path
) -> int:
    """Скачивает объект в файл и возвращает его размер."""
    client.download_file(bucket, key, str(target_path), Config=DOWNLOAD_CONFIG)
    return target_path.stat().st_size


def unpacked_sha256(archive_path: Path) -> tuple[str, int]:
    """Распаковывает gzip в поток и возвращает sha256 и размер."""
    digest = hashlib.sha256()
    size = 0
    with gzip.open(archive_path, "rb") as source:
        chunk = source.read(CHUNK_SIZE)
        while chunk:
            digest.update(chunk)
            size += len(chunk)
            chunk = source.read(CHUNK_SIZE)
    return digest.hexdigest(), size


def stored_checksum(metadata: dict[str, str]) -> str:
    """Возвращает sha256 из метаданных независимо от регистра ключа.

    Yandex Object Storage отдаёт ключ как Sha256, другие хранилища
    могут отдавать sha256, поэтому сравниваем без учёта регистра.
    """
    for name, value in metadata.items():
        if name.lower() == "sha256":
            return value.strip()
    return ""


def format_size(size: int) -> str:
    """Печатает размер в байтах или МБ, смотря что понятнее."""
    if size < MIB:
        return f"{size} байт"
    return f"{size / MIB:.2f} МБ"
