"""Проверка всех S3-хранилищ, описанных в .env.

Хранилище описывается пятью переменными (ИМЯ - любое, например RUSTFS или MINIO):
    S3_<ИМЯ>_HOST          адрес, например localhost
    S3_<ИМЯ>_PORT          порт S3, например 9000
    S3_<ИМЯ>_CONSOLE_PORT  порт консоли (скриптом проверки не используется)
    S3_<ИМЯ>_ACCESS_KEY    логин
    S3_<ИМЯ>_SECRET_KEY    пароль

Чтобы проверить ещё одно хранилище, добавь в .env его пять переменных.
Хранилище находится по переменной S3_<ИМЯ>_HOST. Подключение всегда по http.

Для каждого хранилища выполняются 5 шагов:
1. доступ по ключам (показывает, какой сервер ответил);
2. создание бакетов bronze, silver, если их нет;
3. запись, чтение и листинг небольшого объекта;
4. многочастная загрузка (11 МиБ тремя частями) с проверкой хеша;
5. удаление тестовых объектов.

Запуск из корня проекта:
    uv run --env-file .env python utils/check_s3.py

Скрипт не удаляет бакеты и не трогает объекты вне папки _healthcheck/.
"""

import hashlib
import io
import os
import re
import sys
import uuid

import boto3
from boto3.exceptions import S3UploadFailedError
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

BUCKETS = ("bronze", "silver")
TEST_BUCKET = "bronze"
PREFIX = "_healthcheck/"
MIB = 1024 * 1024
SETTINGS = (
    "HOST",
    "PORT",
    "ACCESS_KEY",
    "SECRET_KEY",
)  # CONSOLE_PORT здесь не нужен

STEP_AUTH = "доступ по ключам"
STEP_BUCKETS = "бакеты bronze, silver"
STEP_ROUNDTRIP = "запись, чтение, листинг"
STEP_MULTIPART = "многочастная загрузка"
STEP_CLEANUP = "удаление тестовых объектов"
STEPS = [STEP_AUTH, STEP_BUCKETS, STEP_ROUNDTRIP, STEP_MULTIPART, STEP_CLEANUP]

# Ошибки, которые считаем провалом шага (а не поломкой самого скрипта).
CHECK_ERRORS = (
    ClientError,
    BotoCoreError,
    S3UploadFailedError,
    AssertionError,
)


def find_storages() -> list[str]:
    """Ищет в окружении переменные S3_<ИМЯ>_HOST и возвращает список имён."""
    names = []
    for variable in os.environ:
        match = re.fullmatch(r"S3_(.+)_HOST", variable)
        if match:
            names.append(match.group(1))
    return sorted(names)


def read_settings(name: str) -> tuple[dict, list[str]]:
    """Читает настройки хранилища. Возвращает (значения, список незаданных переменных)."""
    values = {}
    missing = []
    for setting in SETTINGS:
        variable = f"S3_{name}_{setting}"
        value = os.environ.get(variable, "").strip()
        values[setting] = value
        if not value:
            missing.append(variable)
    return values, missing


def make_client(endpoint: str, access_key: str, secret_key: str):
    """Создаёт клиент boto3 для одного хранилища."""
    config = Config(
        signature_version="s3v4",
        s3={
            "addressing_style": "path"
        },  # адрес вида http://host:порт/бакет/ключ
        retries={"max_attempts": 1, "mode": "standard"},
        connect_timeout=5,
        read_timeout=60,
        # Новые boto3 добавляют контрольные суммы, которые не все хранилища принимают.
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        config=config,
    )


def check_auth(client) -> str:
    response = client.list_buckets()
    server = response["ResponseMetadata"]["HTTPHeaders"].get(
        "server", "не указан"
    )
    return f"Server: {server}, бакетов: {len(response['Buckets'])}"


def ensure_buckets(client) -> str:
    created = []
    for bucket in BUCKETS:
        try:
            client.head_bucket(Bucket=bucket)
        except ClientError as error:
            code = str(error.response["Error"]["Code"])
            if code not in ("404", "NoSuchBucket", "NotFound"):
                raise  # не "бакета нет", а другая ошибка (например, нет доступа)
            client.create_bucket(Bucket=bucket)
            created.append(bucket)
    return f"создано: {created or 'нет, уже существуют'}"


def check_roundtrip(client, key: str) -> str:
    body = f"orbital-data check {uuid.uuid4()}".encode()
    client.put_object(Bucket=TEST_BUCKET, Key=key, Body=body)
    head = client.head_object(Bucket=TEST_BUCKET, Key=key)
    assert head["ContentLength"] == len(body), "размер объекта не совпадает"
    received = client.get_object(Bucket=TEST_BUCKET, Key=key)["Body"].read()
    assert received == body, "прочитанные данные отличаются от записанных"
    listed = client.list_objects_v2(Bucket=TEST_BUCKET, Prefix=PREFIX)
    keys = [item["Key"] for item in listed.get("Contents", [])]
    assert key in keys, "объект не найден в листинге"
    return f"{len(body)} байт"


def check_multipart(client, key: str) -> str:
    payload = os.urandom(11 * MIB)
    expected_hash = hashlib.sha256(payload).hexdigest()
    # Порог и размер части по 5 МиБ: 11 МиБ уйдут тремя частями.
    transfer = TransferConfig(
        multipart_threshold=5 * MIB, multipart_chunksize=5 * MIB
    )
    client.upload_fileobj(
        io.BytesIO(payload), TEST_BUCKET, key, Config=transfer
    )
    received = client.get_object(Bucket=TEST_BUCKET, Key=key)["Body"].read()
    assert len(received) == len(payload), "размер после загрузки не совпадает"
    assert hashlib.sha256(received).hexdigest() == expected_hash, (
        "хеш не совпадает"
    )
    return "11 МиБ тремя частями, хеш совпал"


def cleanup(client, keys: list[str]) -> str:
    for key in keys:
        client.delete_object(Bucket=TEST_BUCKET, Key=key)
    left = client.list_objects_v2(Bucket=TEST_BUCKET, Prefix=PREFIX).get(
        "Contents", []
    )
    assert not left, f"остались объекты: {[item['Key'] for item in left]}"
    return ""


def check_storage(name: str) -> dict:
    """Проверяет одно хранилище. Возвращает {шаг: (успех, подробности)}."""
    results = {}

    def run(step_name: str, action) -> bool:
        """Выполняет шаг, печатает результат и запоминает его."""
        try:
            detail = action()
        except CHECK_ERRORS as error:
            results[step_name] = (False, str(error))
            print(f"[ОШИБКА] {step_name}: {error}")
            return False
        results[step_name] = (True, detail)
        print(f"[OK] {step_name}" + (f": {detail}" if detail else ""))
        return True

    def fail(message: str) -> dict:
        results[STEP_AUTH] = (False, message)
        print(f"[ОШИБКА] {STEP_AUTH}: {message}")
        return results

    values, missing = read_settings(name)
    if missing:
        return fail(f"не заданы переменные: {', '.join(missing)}")
    if not values["PORT"].isdigit():
        return fail(
            f"S3_{name}_PORT должен быть числом, сейчас: {values['PORT']}"
        )

    endpoint = f"http://{values['HOST']}:{values['PORT']}"
    print(f"Адрес: {endpoint}")
    client = make_client(endpoint, values["ACCESS_KEY"], values["SECRET_KEY"])
    small_key = f"{PREFIX}{uuid.uuid4().hex}-small.txt"
    large_key = f"{PREFIX}{uuid.uuid4().hex}-multipart.bin"

    # Без доступа и бакетов дальше идти нет смысла.
    if not run(STEP_AUTH, lambda: check_auth(client)):
        return results
    if not run(STEP_BUCKETS, lambda: ensure_buckets(client)):
        return results

    # Эти два шага независимы: падение одного не скрывает результат другого.
    try:
        run(STEP_ROUNDTRIP, lambda: check_roundtrip(client, small_key))
        run(STEP_MULTIPART, lambda: check_multipart(client, large_key))
    finally:
        run(STEP_CLEANUP, lambda: cleanup(client, [small_key, large_key]))
    return results


def print_summary(all_results: dict) -> bool:
    """Печатает итоговую таблицу. Возвращает True, если всё прошло успешно."""
    names = list(all_results)
    print("\nИтог:")
    print("Шаг".ljust(30) + "".join(name.ljust(14) for name in names))
    all_ok = True
    for step_name in STEPS:
        row = step_name.ljust(30)
        for name in names:
            outcome = all_results[name].get(step_name)
            if outcome is None:
                text = "пропущено"
            elif outcome[0]:
                text = "OK"
            else:
                text = "ОШИБКА"
            if text != "OK":
                all_ok = False
            row += text.ljust(14)
        print(row)
    return all_ok


def main() -> None:
    names = find_storages()
    if not names:
        sys.exit(
            "В окружении нет переменных S3_<ИМЯ>_HOST. "
            "Добавь хранилище в .env (HOST, PORT, ACCESS_KEY, SECRET_KEY) "
            "и запусти через uv run --env-file .env"
        )
    print(
        f"Найдено хранилищ: {len(names)} ({', '.join(name.lower() for name in names)})"
    )

    all_results = {}
    for name in names:
        print(f"\n== {name.lower()} ==")
        all_results[name.lower()] = check_storage(name)

    all_ok = print_summary(all_results)
    print("\nПроверка пройдена" if all_ok else "\nПроверка не пройдена")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
