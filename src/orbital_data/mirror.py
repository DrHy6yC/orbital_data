"""Копирование объектов Bronze и Silver из источника в приёмник.

Копирование идёт по тем же ключам. Объект с совпадающим размером
пропускается, объект с другим размером перезаписывается. Ничего
не удаляется: лишние объекты в приёмнике остаются на месте.
"""

from dataclasses import dataclass, field

from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from orbital_data.s3_access import StorageError

BUCKETS = ("bronze", "silver")
MISSING_CODES = ("404", "NoSuchBucket", "NoSuchKey", "NotFound")


@dataclass
class CopyResult:
    """Что скопировано, что пропущено и где ошибки."""

    dry_run: bool = False
    copied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


def list_objects(client: BaseClient, bucket: str) -> list[tuple[str, int]]:
    """Возвращает ключи и размеры всех объектов бакета."""
    items = []
    token = ""
    while True:
        arguments = {"Bucket": bucket}
        if token:
            arguments["ContinuationToken"] = token
        response = client.list_objects_v2(**arguments)
        for item in response.get("Contents", []):
            items.append((item["Key"], item["Size"]))
        if not response.get("IsTruncated"):
            break
        token = response["NextContinuationToken"]
    return items


def read_object_size(client: BaseClient, bucket: str, key: str) -> int | None:
    """Возвращает размер объекта или None, если объекта нет."""
    try:
        response = client.head_object(Bucket=bucket, Key=key)
    except ClientError as error:
        code = str(error.response["Error"]["Code"])
        if code in MISSING_CODES:
            return None
        raise
    return response["ContentLength"]


def ensure_bucket(client: BaseClient, bucket: str) -> None:
    """Создаёт бакет, если его нет."""
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as error:
        code = str(error.response["Error"]["Code"])
        if code in MISSING_CODES:
            client.create_bucket(Bucket=bucket)
        else:
            raise


def mirror_object(
    source_client: BaseClient,
    target_client: BaseClient,
    bucket: str,
    key: str,
    size: int,
    is_dry_run: bool,
) -> bool:
    """Копирует объект, если его нет в приёмнике или размер другой."""
    if read_object_size(target_client, bucket, key) == size:
        return False
    if is_dry_run:
        return True
    body = source_client.get_object(Bucket=bucket, Key=key)["Body"]
    target_client.upload_fileobj(body, bucket, key)
    copied_size = read_object_size(target_client, bucket, key)
    if copied_size != size:
        raise StorageError(
            f"{bucket}/{key}: после копирования размер "
            f"{copied_size}, ожидался {size}"
        )
    return True


def mirror_buckets(
    source_client: BaseClient,
    target_client: BaseClient,
    buckets: tuple[str, ...] = BUCKETS,
    is_dry_run: bool = False,
) -> CopyResult:
    """Копирует объекты выбранных бакетов из источника в приёмник."""
    result = CopyResult(dry_run=is_dry_run)
    for bucket in buckets:
        try:
            if not is_dry_run:
                ensure_bucket(target_client, bucket)
            items = list_objects(source_client, bucket)
        except (ClientError, BotoCoreError) as error:
            result.errors[bucket] = str(error)
            continue
        for key, size in items:
            name = f"{bucket}/{key}"
            try:
                copied = mirror_object(
                    source_client,
                    target_client,
                    bucket,
                    key,
                    size,
                    is_dry_run,
                )
            except (ClientError, BotoCoreError, StorageError) as error:
                result.errors[name] = str(error)
                continue
            if copied:
                result.copied.append(name)
            else:
                result.skipped.append(name)
    return result
