"""Проверка загрузки: пять наборов сохраняются в data/ и в Bronze.

Скрипт нужен для живой проверки задач 3.4 и 4.4.
Запуск из корня проекта (учётные данные берутся из .env):
    uv run --env-file .env python utils/check_download.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orbital_data.collectors.celestrak import CelesTrakClient  # noqa: E402
from orbital_data.collectors.download import (  # noqa: E402
    DownloadResult,
    download_datasets,
)
from orbital_data.collectors.space_track import SpaceTrackClient  # noqa: E402
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
    with CelesTrakClient() as celestrak:
        with SpaceTrackClient.from_env() as space_track:
            result = download_datasets(
                celestrak, space_track, data_directory, uploader
            )
    show_result(result)
    if result.errors:
        sys.exit(1)


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
