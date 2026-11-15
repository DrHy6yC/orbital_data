"""Получение и сохранение исходных ответов по выбранным наборам данных.

Наборы описаны в docs/data_sources/datasets.md. Каждый набор сохраняется
сразу после получения, чтобы не держать в памяти все ответы: один набор
space_track_gp занимает около 76 МБ.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from orbital_data.collectors.celestrak import CelesTrakClient
from orbital_data.collectors.errors import SourceStopped
from orbital_data.collectors.space_track import SpaceTrackClient
from orbital_data.source_snapshots.save import save_original

CELESTRAK_DATASETS = {
    "STATIONS": ("celestrak/gp_stations", "csv"),
    "ACTIVE": ("celestrak/gp_active", "csv"),
}

SPACE_TRACK_DATASETS = {
    "gp": ("space_track/gp", "json"),
    "satcat": ("space_track/satcat", "json"),
    "decay": ("space_track/decay", "json"),
}


@dataclass
class DownloadResult:
    """Что сохранено и на чём остановился каждый источник."""

    datasets: dict[str, Path] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


def download_datasets(
    celestrak_client: CelesTrakClient,
    space_track_client: SpaceTrackClient,
    data_directory: Path,
) -> DownloadResult:
    """Скачивает наборы по источникам и сразу сохраняет каждый.

    При отказе источника его оставшиеся наборы не запрашиваются,
    второй источник загружается полностью.
    """
    result = DownloadResult()
    timestamp = current_timestamp()
    for group, (folder, extension) in CELESTRAK_DATASETS.items():
        file_path = make_dataset_path(
            data_directory, folder, extension, timestamp
        )
        try:
            body = celestrak_client.fetch_gp(group)
        except SourceStopped as error:
            result.errors["celestrak"] = str(error)
            break
        result.datasets[folder] = save_original(body, file_path)
    for api_class, (folder, extension) in SPACE_TRACK_DATASETS.items():
        file_path = make_dataset_path(
            data_directory, folder, extension, timestamp
        )
        try:
            body = space_track_client.fetch(api_class)
        except SourceStopped as error:
            result.errors["space_track"] = str(error)
            break
        result.datasets[folder] = save_original(body, file_path)
    return result


def make_dataset_path(
    data_directory: Path,
    folder: str,
    extension: str,
    timestamp: str,
) -> Path:
    """Путь файла набора: каталог набора и время получения."""
    return data_directory / folder / f"{timestamp}.{extension}"


def current_timestamp() -> str:
    """Время получения в UTC в виде, пригодном для имени файла."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
