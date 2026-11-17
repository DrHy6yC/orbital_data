"""Минимальная проверка доступа к Yandex Object Storage (как в примере из документации).

Читает BACKUP_S3_* из .env, выводит первые 10 объектов бакета, а при ошибке
печатает код и сообщение сервера. Секретный ключ не печатается.

Запуск из корня проекта:
    uv run --env-file .env python utils/yandex_probe.py
"""

import os
import sys

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


def get(name: str) -> str:
    raw = os.environ.get(name, "")
    value = raw.strip()
    if not value:
        sys.exit(f"Не задана переменная {name}")
    if raw != value:
        print(
            f"[ПРЕДУПРЕЖДЕНИЕ] {name}: лишние пробелы по краям значения, они убраны"
        )
    return value


endpoint = get("BACKUP_S3_ENDPOINT")
region = get("BACKUP_S3_REGION")
bucket = get("BACKUP_S3_BUCKET")
key_id = get("BACKUP_S3_ACCESS_KEY")
secret = get("BACKUP_S3_SECRET_KEY")

# Идентификатор ключа не секрет: печатаем его, чтобы сверить с консолью.
print(
    f"Ключ: {key_id}, длина секрета: {len(secret)}, бакет: {bucket}, регион: {region}"
)

client = boto3.client(
    "s3",
    endpoint_url=endpoint,
    region_name=region,
    aws_access_key_id=key_id,
    aws_secret_access_key=secret,
    config=Config(s3={"addressing_style": "path"}),
)

try:
    result = client.list_objects_v2(Bucket=bucket, MaxKeys=10)
except ClientError as error:
    info = error.response["Error"]
    request_id = error.response["ResponseMetadata"].get("RequestId", "-")
    sys.exit(
        f"[ОШИБКА] {info.get('Code')}: {info.get('Message')} (RequestId {request_id})"
    )
except BotoCoreError as error:
    sys.exit(f"[ОШИБКА] {error}")

objects = result.get("Contents", [])
print(f"[OK] Объектов в списке: {len(objects)}")
for obj in objects:
    print(obj["Key"])
