"""Выгрузка сохранённых снимков в бакет bronze основного хранилища.

Настройки берутся из переменных S3_RUSTFS_* в .env:
    S3_RUSTFS_HOST, S3_RUSTFS_PORT,
    S3_RUSTFS_ACCESS_KEY, S3_RUSTFS_SECRET_KEY.

Ключ объекта повторяет путь локального снимка относительно data/:
    space_track/gp/2026-11-16T15-19-04Z.json
"""

import os
from dataclasses import dataclass
from pathlib import Path

import boto3
from boto3.exceptions import S3UploadFailedError
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

BUCKET = "bronze"
PREFIX = "S3_RUSTFS"
SETTINGS = ("HOST", "PORT", "ACCESS_KEY", "SECRET_KEY")


class UploadError(RuntimeError):
    """Выгрузка снимка не удалась."""


def read_settings() -> dict[str, str]:
    """Читает настройки хранилища из окружения."""
    values = {}
    missing = []
    for setting in SETTINGS:
        variable = f"{PREFIX}_{setting}"
        value = os.environ.get(variable, "").strip()
        values[setting] = value
        if not value:
            missing.append(variable)
    if missing:
        raise UploadError("Не заданы переменные: " + ", ".join(missing))
    if not values["PORT"].isdigit():
        raise UploadError(
            f"{PREFIX}_PORT должен быть числом: {values['PORT']}"
        )
    return values


def make_client(values: dict[str, str]) -> BaseClient:
    """Создаёт клиент boto3 для основного хранилища."""
    endpoint = f"http://{values['HOST']}:{values['PORT']}"
    config = Config(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        # Новые boto3 добавляют контрольные суммы, которые не все
        # хранилища принимают.
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=values["ACCESS_KEY"],
        aws_secret_access_key=values["SECRET_KEY"],
        region_name="us-east-1",
        config=config,
    )


def make_key(file_path: Path, data_directory: Path) -> str:
    """Ключ объекта: путь снимка относительно каталога data/."""
    try:
        relative_path = file_path.resolve().relative_to(
            data_directory.resolve()
        )
    except ValueError as error:
        raise UploadError(f"Файл вне каталога данных: {file_path}") from error
    return relative_path.as_posix()


@dataclass
class SnapshotUploader:
    """Выгружает снимки в бакет bronze."""

    client: BaseClient
    bucket: str = BUCKET

    @classmethod
    def from_env(cls) -> "SnapshotUploader":
        """Создаёт загрузчик по настройкам из окружения."""
        return cls(client=make_client(read_settings()))

    def upload(self, file_path: Path, data_directory: Path) -> str:
        """Выгружает файл и возвращает ключ объекта."""
        key = make_key(file_path, data_directory)
        try:
            self.client.upload_file(str(file_path), self.bucket, key)
        except (
            ClientError,
            BotoCoreError,
            S3UploadFailedError,
        ) as error:
            raise UploadError(f"{key}: {error}") from error
        return key
