"""Восстановление снимков Bronze из облака в RustFS.

Скрипт берёт объект бэкапа `bronze/<источник>/<набор>/<время>.<расширение>.gz`,
скачивает его, распаковывает gzip, сверяет sha256 с метаданными объекта
и со `checksum_sha256` снимка в базе, затем загружает файл в RustFS
под ключом без `bronze/` и без `.gz`. Сама операция живёт
в `orbital_data.cloud_restore`.

По умолчанию восстанавливается последний снимок каждого набора.
Ключ --dataset ограничивает работу одним набором: `space_track/gp`.
Ключ --dry-run печатает план без скачивания и записи.

В облаке выполняются только LIST, HEAD и GET.
Дамп PostgreSQL восстанавливается до запуска: без таблицы `snapshots`
не с чем связать отметки копий.

Запуск из корня проекта:
    uv run --env-file .env python utils/restore_from_cloud.py --dry-run
    uv run --env-file .env python utils/restore_from_cloud.py
    uv run --env-file .env python utils/restore_from_cloud.py --dataset
        celestrak/gp_stations
"""

import argparse
import sys
import tempfile
from pathlib import Path

import psycopg
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from orbital_data.backup_retention import snapshot_key  # noqa: E402
from orbital_data.cloud_objects import (  # noqa: E402
    format_size,
    list_cloud_keys,
    make_cloud_client,
    read_required_env,
)
from orbital_data.cloud_restore import (  # noqa: E402
    BRONZE_BUCKET,
    newest_keys,
    parse_dataset,
    restore_object,
)
from orbital_data.s3_access import (  # noqa: E402
    StorageError,
    make_client,
    read_settings,
)
from orbital_data.source_snapshots.registry import (  # noqa: E402
    RegistryError,
    connect,
    ensure_primary_copy,
    snapshot_checksums,
)

RUSTFS = "RUSTFS"


def dataset_argument(value: str) -> str:
    """Преобразует значение --dataset в формат argparse."""
    try:
        return parse_dataset(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def open_registry() -> psycopg.Connection | None:
    """Открывает базу метаданных; без неё восстановление продолжается."""
    try:
        return connect()
    except (RegistryError, psycopg.Error) as error:
        print(f"метаданные: ошибка — {error}")
        return None


def read_checksums(
    connection: psycopg.Connection | None, object_keys: list[str]
) -> dict[str, str]:
    """Читает сохранённые sha256 снимков, если база доступна."""
    if connection is None:
        return {}
    try:
        return snapshot_checksums(connection, object_keys)
    except psycopg.Error as error:
        print(f"метаданные: ошибка — {error}")
        return {}


def mark_restored(
    connection: psycopg.Connection | None, object_key: str, size: int
) -> None:
    """Отмечает восстановленную копию в базе, если она доступна."""
    if connection is None:
        return
    try:
        if ensure_primary_copy(connection, object_key, size):
            print("  отметка в базе: добавлена копия rustfs")
    except psycopg.Error as error:
        print(f"метаданные: ошибка — {error}")


def show_plan(
    cloud: BaseClient, cloud_bucket: str, cloud_keys: list[str]
) -> None:
    """Печатает, что будет восстановлено, без скачивания."""
    for cloud_key in cloud_keys:
        head = cloud.head_object(Bucket=cloud_bucket, Key=cloud_key)
        packed = head["ContentLength"]
        print(f"восстановил бы: {BRONZE_BUCKET}/{snapshot_key(cloud_key)}")
        print(f"  из {cloud_key}, сжато {format_size(packed)}")


def main() -> None:
    """Восстанавливает снимки Bronze из облака в RustFS."""
    parser = argparse.ArgumentParser(
        description=(
            "Восстанавливает снимки Bronze из облака в RustFS: "
            "по умолчанию последний снимок каждого набора"
        ),
    )
    parser.add_argument(
        "--dataset",
        type=dataset_argument,
        help="один набор в формате источник/набор, например space_track/gp",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="показать план без скачивания и записи",
    )
    args = parser.parse_args()

    cloud_bucket = read_required_env("BACKUP_S3_BUCKET")
    cloud = make_cloud_client()
    try:
        cloud_keys = list_cloud_keys(cloud, cloud_bucket)
    except (ClientError, BotoCoreError) as error:
        sys.exit(f"[ОШИБКА] не удалось прочитать бакет: {error}")

    selected = newest_keys(cloud_keys, args.dataset)
    if not selected:
        if args.dataset:
            sys.exit(f"В облаке нет снимков набора {args.dataset}")
        sys.exit("В облаке нет снимков для восстановления")

    if args.dry_run:
        show_plan(cloud, cloud_bucket, selected)
        return

    try:
        storage = make_client(read_settings(RUSTFS))
    except StorageError as error:
        sys.exit(f"RustFS не настроен: {error}")

    print(f"Объектов к восстановлению: {len(selected)}")
    connection = open_registry()
    checksums = read_checksums(
        connection, [snapshot_key(key) for key in selected]
    )

    ok = 0
    errors = 0
    with tempfile.TemporaryDirectory() as temp_directory:
        for cloud_key in selected:
            try:
                size = restore_object(
                    cloud,
                    storage,
                    cloud_bucket,
                    cloud_key,
                    Path(temp_directory),
                    checksums,
                )
            except (
                ClientError,
                BotoCoreError,
                StorageError,
                OSError,
            ) as error:
                print(f"{cloud_key}\n  [ОШИБКА] {error}")
                errors += 1
                continue
            if size is None:
                errors += 1
                continue
            ok += 1
            mark_restored(connection, snapshot_key(cloud_key), size)

    if connection is not None:
        connection.close()
    print(f"\nуспешно: {ok}, ошибок: {errors}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
