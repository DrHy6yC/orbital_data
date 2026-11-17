"""Выгрузка сохранённых снимков в бакет bronze основного хранилища.

Настройки берутся из переменных S3_RUSTFS_* в .env:
    S3_RUSTFS_HOST, S3_RUSTFS_PORT,
    S3_RUSTFS_ACCESS_KEY, S3_RUSTFS_SECRET_KEY.

Ключ объекта повторяет путь локального снимка относительно data/:
    space_track/gp/2026-11-16T15-19-04Z.json
"""

from dataclasses import dataclass
from pathlib import Path

from boto3.exceptions import S3UploadFailedError
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from orbital_data.s3_access import (
    StorageError,
    make_client,
    read_settings,
)

BUCKET = "bronze"
STORAGE = "RUSTFS"

# Для вызывающего кода настройки и выгрузка — одна операция,
# поэтому прежнее имя ошибки сохранено.
UploadError = StorageError


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
        return cls(client=make_client(read_settings(STORAGE)))

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
