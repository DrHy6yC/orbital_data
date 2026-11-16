"""Проверка подключения к S3-хранилищу (RustFS): доступ, бакеты, запись и чтение.

Шаги:
1. доступ по ключам (список бакетов);
2. создание бакетов bronze, silver, gold, если их нет;
3. запись, чтение, проверка размера и листинг небольшого объекта;
4. многочастная загрузка (11 МиБ тремя частями) с проверкой хеша;
5. удаление тестовых объектов.

Запуск из корня проекта (ключи берутся из .env):
    uv run --env-file .env python utils/check_s3.py

Адрес по умолчанию http://localhost:9000, можно переопределить переменной S3_ENDPOINT_URL.
Скрипт не удаляет бакеты и не трогает объекты вне префикса _healthcheck/.
"""

import hashlib
import io
import os
import sys
import uuid

import boto3
from boto3.exceptions import S3UploadFailedError
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

ENDPOINT = os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000")
BUCKETS = ("bronze", "silver", "gold")
TEST_BUCKET = "bronze"
PREFIX = "_healthcheck/"
MIB = 1024 * 1024
CHECK_ERRORS = (ClientError, BotoCoreError, S3UploadFailedError, AssertionError)


def make_client():
    try:
        access_key = os.environ["S3_ACCESS_KEY"]
        secret_key = os.environ["S3_SECRET_KEY"]
    except KeyError as error:
        sys.exit(f"Не задана переменная окружения {error.args[0]}")
    config = Config(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        retries={"max_attempts": 1, "mode": "standard"},
        connect_timeout=5,
        read_timeout=60,
        # Новые версии boto3 по умолчанию добавляют контрольные суммы,
        # которые часть S3-совместимых хранилищ не принимает.
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    )
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        config=config,
    )


def step(title, action):
    try:
        result = action()
    except CHECK_ERRORS as error:
        print(f"[ОШИБКА] {title}: {error}")
        sys.exit(1)
    print(f"[OK] {title}" + (f": {result}" if result else ""))


def check_auth(client):
    names = [bucket["Name"] for bucket in client.list_buckets()["Buckets"]]
    return f"бакетов в хранилище: {len(names)}"


def ensure_buckets(client):
    created = []
    for name in BUCKETS:
        try:
            client.head_bucket(Bucket=name)
        except ClientError as error:
            code = str(error.response["Error"]["Code"])
            if code not in ("404", "NoSuchBucket", "NotFound"):
                raise
            client.create_bucket(Bucket=name)
            created.append(name)
    return f"создано: {created or 'нет, уже существуют'}"


def roundtrip(client, key):
    body = f"orbital-data check {uuid.uuid4()}".encode("utf-8")
    client.put_object(Bucket=TEST_BUCKET, Key=key, Body=body)
    head = client.head_object(Bucket=TEST_BUCKET, Key=key)
    assert head["ContentLength"] == len(body), "размер объекта не совпадает"
    received = client.get_object(Bucket=TEST_BUCKET, Key=key)["Body"].read()
    assert received == body, "прочитанные данные отличаются от записанных"
    listed = client.list_objects_v2(Bucket=TEST_BUCKET, Prefix=PREFIX)
    keys = [item["Key"] for item in listed.get("Contents", [])]
    assert key in keys, "объект не найден в листинге"
    return f"{len(body)} байт"


def multipart(client, key):
    payload = os.urandom(11 * MIB)
    expected = hashlib.sha256(payload).hexdigest()
    transfer = TransferConfig(multipart_threshold=5 * MIB, multipart_chunksize=5 * MIB)
    client.upload_fileobj(io.BytesIO(payload), TEST_BUCKET, key, Config=transfer)
    received = client.get_object(Bucket=TEST_BUCKET, Key=key)["Body"].read()
    assert len(received) == len(payload), "размер после загрузки не совпадает"
    assert hashlib.sha256(received).hexdigest() == expected, "хеш данных не совпадает"
    return "11 МиБ тремя частями, хеш совпал"


def cleanup(client, keys):
    try:
        for key in keys:
            client.delete_object(Bucket=TEST_BUCKET, Key=key)
        left = client.list_objects_v2(Bucket=TEST_BUCKET, Prefix=PREFIX).get("Contents", [])
        assert not left, f"остались объекты: {[item['Key'] for item in left]}"
        print("[OK] удаление тестовых объектов")
    except CHECK_ERRORS as error:
        print(f"[ПРЕДУПРЕЖДЕНИЕ] очистка не завершена: {error}")


def main():
    client = make_client()
    print(f"Адрес: {ENDPOINT}")
    small_key = f"{PREFIX}{uuid.uuid4().hex}-small.txt"
    large_key = f"{PREFIX}{uuid.uuid4().hex}-multipart.bin"

    step("доступ по ключам", lambda: check_auth(client))
    step("бакеты bronze, silver, gold", lambda: ensure_buckets(client))
    try:
        step("запись, чтение, листинг", lambda: roundtrip(client, small_key))
        step("многочастная загрузка", lambda: multipart(client, large_key))
    finally:
        cleanup(client, [small_key, large_key])
    print("Проверка пройдена")


if __name__ == "__main__":
    main()