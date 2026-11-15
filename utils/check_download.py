"""Проверка загрузки: пять наборов из двух источников, размеры ответов.

Скрипт ничего не сохраняет, он нужен только для проверки задачи 3.2.
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


def main() -> None:
    with CelesTrakClient() as celestrak:
        with SpaceTrackClient.from_env() as space_track:
            result = download_datasets(celestrak, space_track)
    show_result(result)
    if result.errors:
        sys.exit(1)


def show_result(result: DownloadResult) -> None:
    for name, body in result.datasets.items():
        print(f"{name}: {len(body)} байт")
    for source, message in result.errors.items():
        print(f"{source}: ошибка — {message}")


if __name__ == "__main__":
    main()
