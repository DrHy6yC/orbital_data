"""Проверка загрузки: снимки в data/, Bronze и метаданные PostgreSQL.

Скрипт нужен для живой проверки задач 3.4, 4.4 и 4.7.
Запуск из корня проекта (учётные данные берутся из .env):
    uv run --env-file .env python utils/check_download.py
"""

import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orbital_data.collectors.celestrak import CelesTrakClient  # noqa: E402
from orbital_data.collectors.download import (  # noqa: E402
    DownloadResult,
    download_datasets,
)
from orbital_data.collectors.space_track import SpaceTrackClient  # noqa: E402
from orbital_data.source_snapshots.registry import (  # noqa: E402
    RegistryError,
    RunRegistry,
    define_status,
    parse_fetched_at,
)
from orbital_data.source_snapshots.upload import (  # noqa: E402
    BUCKET,
    SnapshotUploader,
    UploadError,
)


def main() -> None:
    data_directory = Path(__file__).resolve().parent.parent / "data"
    try:
        uploader = SnapshotUploader.from_env()
    except UploadError as error:
        sys.exit(f"Хранилище не настроено: {error}")
    registry = open_registry()
    with CelesTrakClient() as celestrak:
        with SpaceTrackClient.from_env() as space_track:
            result = download_datasets(
                celestrak, space_track, data_directory, uploader
            )
    show_result(result)
    if registry is not None:
        save_metadata(registry, result)
    if result.errors:
        sys.exit(1)


def open_registry() -> RunRegistry | None:
    """Открывает прогон; без базы загрузка продолжается."""
    try:
        return RunRegistry.start()
    except (RegistryError, psycopg.Error) as error:
        print(f"метаданные: ошибка — {error}")
        return None


def save_metadata(registry: RunRegistry, result: DownloadResult) -> None:
    """Записывает снимки, копии в RustFS и итог прогона."""
    try:
        for folder, file_path in result.datasets.items():
            snapshot_id = registry.add_snapshot(
                folder, file_path, parse_fetched_at(file_path)
            )
            key = result.uploads.get(folder)
            if key:
                registry.add_copy(snapshot_id, "rustfs", key)
        message = "; ".join(
            f"{name}: {error}" for name, error in result.errors.items()
        )
        registry.finish(
            define_status(len(result.datasets), len(result.errors)),
            message,
        )
    except (RegistryError, psycopg.Error) as error:
        print(f"метаданные: ошибка — {error}")
    finally:
        registry.close()


def show_result(result: DownloadResult) -> None:
    for folder, file_path in result.datasets.items():
        size = file_path.stat().st_size
        print(f"{folder}: {size} байт -> {file_path}")
        key = result.uploads.get(folder)
        if key:
            print(f"    {BUCKET}/{key}")
    for source, message in result.errors.items():
        print(f"{source}: ошибка — {message}")


if __name__ == "__main__":
    main()
