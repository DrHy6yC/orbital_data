"""Копирует объекты Bronze и Silver из RustFS в MinIO.

Ничего не удаляет, повторный запуск не копирует уже скопированное.
Запуск из корня проекта:
    uv run --env-file .env python utils/sync_storage.py --dry-run
    uv run --env-file .env python utils/sync_storage.py
    uv run --env-file .env python utils/sync_storage.py --bucket bronze
"""

import argparse
import sys
from pathlib import Path

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

SOURCE = "RUSTFS"
TARGET = "MINIO"


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
    if result.errors:
        sys.exit(1)


def show_result(result: CopyResult) -> None:
    item_label = "копировать" if result.dry_run else "скопирован"
    for name in result.copied:
        print(f"{item_label}: {name}")
    for name in result.skipped:
        print(f"уже на месте: {name}")
    for name, message in result.errors.items():
        print(f"ошибка {name}: {message}")
    summary = "по плану" if result.dry_run else "скопировано"
    print(
        f"\n{summary}: {len(result.copied)}, "
        f"уже было: {len(result.skipped)}, "
        f"ошибок: {len(result.errors)}"
    )


if __name__ == "__main__":
    main()
