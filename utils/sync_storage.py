"""Копирует объекты Bronze и Silver из RustFS в MinIO.

Ничего не удаляет, повторный запуск не копирует уже скопированное.
Копии объектов Bronze отмечаются в orbital.snapshot_copies.
Запуск из корня проекта:
    uv run --env-file .env python utils/sync_storage.py --dry-run
    uv run --env-file .env python utils/sync_storage.py
    uv run --env-file .env python utils/sync_storage.py --bucket bronze
"""

import argparse
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orbital_data.mirror import (  # noqa: E402
    BUCKETS,
    CopyResult,
    mirror_buckets,
)
from orbital_data.s3_access import (  # noqa: E402
    StorageError,
    make_client,
    read_settings,
)
from orbital_data.source_snapshots.registry import (  # noqa: E402
    RegistryError,
    connect,
    save_copy_for_key,
)

SOURCE = "RUSTFS"
TARGET = "MINIO"
TARGET_STORAGE = "minio"
BRONZE_PREFIX = "bronze/"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Копирует объекты RustFS в MinIO без удалений",
    )
    parser.add_argument(
        "--bucket",
        choices=("bronze", "silver", "all"),
        default="all",
        help="какие бакеты копировать, по умолчанию все",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="показать план копирования без записи",
    )
    args = parser.parse_args()

    try:
        source_client = make_client(read_settings(SOURCE))
        target_client = make_client(read_settings(TARGET))
    except StorageError as error:
        sys.exit(f"Хранилище не настроено: {error}")

    buckets = BUCKETS if args.bucket == "all" else (args.bucket,)
    result = mirror_buckets(
        source_client, target_client, buckets, args.dry_run
    )
    show_result(result)
    if not args.dry_run:
        save_copies(result)
    if result.errors:
        sys.exit(1)


def save_copies(result: CopyResult) -> None:
    """Отмечает объекты Bronze, которые уже лежат в MinIO.

    Учитываются и скопированные сейчас, и пропущенные как уже
    существующие: если в прошлый раз база была недоступна, строка
    дописывается при следующем запуске.
    """
    names = [
        name
        for name in result.copied + result.skipped
        if name.startswith(BRONZE_PREFIX)
    ]
    if not names:
        return
    try:
        connection = connect()
    except (RegistryError, psycopg.Error) as error:
        print(f"метаданные: ошибка — {error}")
        return
    marked = 0
    try:
        for name in names:
            object_key = name.removeprefix(BRONZE_PREFIX)
            if save_copy_for_key(connection, TARGET_STORAGE, object_key):
                marked += 1
    except psycopg.Error as error:
        print(f"метаданные: ошибка — {error}")
    finally:
        connection.close()
    print(
        f"копии в MinIO: отмечено новых {marked} "
        f"из {len(names)} объектов Bronze"
    )


def show_result(result: CopyResult) -> None:
    item_label = "копировать" if result.dry_run else "скопирован"
    for name in result.copied:
        print(f"{item_label}: {name}")
    for name in result.skipped:
        print(f"уже на месте: {name}")
    for name, error_message in result.errors.items():
        print(f"ошибка {name}: {error_message}")
    summary = "по плану" if result.dry_run else "скопировано"
    print(
        f"\n{summary}: {len(result.copied)}, "
        f"уже было: {len(result.skipped)}, "
        f"ошибок: {len(result.errors)}"
    )


if __name__ == "__main__":
    main()
