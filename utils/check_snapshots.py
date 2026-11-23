"""Сверка объектов бакета bronze с таблицей orbital.snapshots.

Скрипт собирает ключи и размеры объектов bronze в RustFS и MinIO
и сравнивает их с orbital.snapshots. Печатаются три списка:

- объекты без строки в snapshots;
- строки snapshots без объекта;
- объекты, размер которых отличается от записанного.

Ничего не записывается и не удаляется: только отчёт. Записи задним
числом и удаление объектов выполняются вручную по отчёту.

Запуск из корня проекта:
    uv run --env-file .env python utils/check_snapshots.py

Код возврата: 0 — расхождений нет, 1 — расхождения или ошибка чтения.
Настройки в .env: S3_RUSTFS_*, S3_MINIO_*, POSTGRES_*.
"""

import sys
from pathlib import Path

import psycopg
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orbital_data.mirror import SKIP_PREFIX, list_objects  # noqa: E402
from orbital_data.s3_access import (  # noqa: E402
    StorageError,
    make_client,
    read_settings,
)
from orbital_data.source_snapshots.registry import (  # noqa: E402
    RegistryError,
    SnapshotDiff,
    compare_snapshots,
    connect,
    snapshot_sizes,
)

STORAGES = ("RUSTFS", "MINIO")
BUCKET = "bronze"


def bronze_objects(client: BaseClient) -> dict[str, int]:
    """Возвращает ключи и размеры объектов bronze без служебных."""
    return {
        key: size
        for key, size in list_objects(client, BUCKET)
        if not key.startswith(SKIP_PREFIX)
    }


def show_keys(title: str, keys: list[str]) -> None:
    """Печатает список ключей с количеством."""
    print(f"  {title}: {len(keys)}")
    for key in keys:
        print(f"    {key}")


def show_diff(name: str, object_count: int, diff: SnapshotDiff) -> None:
    """Печатает расхождения одного хранилища."""
    print(f"\n{name}: объектов {object_count}")
    show_keys("объекты без строки в snapshots", diff.without_row)
    show_keys("строки без объекта", diff.without_object)
    print(f"  размер не совпадает: {len(diff.size_mismatch)}")
    for key, stored_size, snapshot_size in diff.size_mismatch:
        print(
            f"    {key}: в хранилище {stored_size}, "
            f"в snapshots {snapshot_size}"
        )
    if not diff.has_differences:
        print("  расхождений нет")


def main() -> None:
    try:
        clients = {name: make_client(read_settings(name)) for name in STORAGES}
    except StorageError as error:
        sys.exit(f"Хранилище не настроено: {error}")
    try:
        connection = connect()
    except (RegistryError, psycopg.Error) as error:
        sys.exit(f"Метаданные недоступны: {error}")
    try:
        snapshots = snapshot_sizes(connection)
    except psycopg.Error as error:
        sys.exit(f"Не удалось прочитать snapshots: {error}")
    finally:
        connection.close()
    print(f"Снимков в orbital.snapshots: {len(snapshots)}")

    failed = False
    for name in STORAGES:
        try:
            objects = bronze_objects(clients[name])
        except (ClientError, BotoCoreError) as error:
            print(f"\n{name}: ошибка чтения — {error}")
            failed = True
            continue
        diff = compare_snapshots(objects, snapshots)
        show_diff(name, len(objects), diff)
        failed = failed or diff.has_differences

    print()
    if failed:
        print("ИТОГ: расхождения есть")
        sys.exit(1)
    print("ИТОГ: расхождений нет")


if __name__ == "__main__":
    main()
