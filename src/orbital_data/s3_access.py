"""Настройки и клиент S3-хранилища из переменных S3_<ИМЯ>_*."""

import os

import boto3
from botocore.client import BaseClient
from botocore.config import Config

SETTINGS = ("HOST", "PORT", "ACCESS_KEY", "SECRET_KEY")


class StorageError(RuntimeError):
    """Обращение к S3-хранилищу не удалось."""


def read_settings(name: str) -> dict[str, str]:
    """Читает настройки хранилища S3_<ИМЯ>_* из окружения."""
    values = {}
    missing = []
    for setting in SETTINGS:
        variable = f"S3_{name}_{setting}"
        value = os.environ.get(variable, "").strip()
        values[setting] = value
        if not value:
            missing.append(variable)
    if missing:
        raise StorageError("Не заданы переменные: " + ", ".join(missing))
    if not values["PORT"].isdigit():
        raise StorageError(
            f"S3_{name}_PORT должен быть числом: {values['PORT']}"
        )
    return values


def make_client(values: dict[str, str]) -> BaseClient:
    """Создаёт клиент boto3 для одного хранилища."""
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
