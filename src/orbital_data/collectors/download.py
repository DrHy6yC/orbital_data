"""Получение и сохранение исходных ответов по выбранным наборам данных.

Наборы описаны в docs/data_sources/datasets.md. Каждый набор сохраняется
сразу после получения, чтобы не держать в памяти все ответы: один набор
space_track_gp занимает около 76 МБ.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from orbital_data.collectors.celestrak import CelesTrakClient
from orbital_data.collectors.errors import SourceStopped
from orbital_data.collectors.space_track import SpaceTrackClient
from orbital_data.collectors.windows import skip_reason
from orbital_data.source_snapshots.save import save_original
from orbital_data.source_snapshots.upload import (
    SnapshotUploader,
    UploadError,
)

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
    """Что сохранено, куда выгружено и на чём остановился источник."""

    datasets: dict[str, Path] = field(default_factory=dict)
    uploads: dict[str, str] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


def download_datasets(
    celestrak_client: CelesTrakClient,
    space_track_client: SpaceTrackClient,
    data_directory: Path,
    uploader: SnapshotUploader | None = None,
    *,
    last_fetches: dict[str, datetime],
    now: datetime | None = None,
) -> DownloadResult:
    """Скачивает наборы по источникам и сразу сохраняет каждый.

    Набор пропускается, если его окно запросов ещё не прошло.
    При отказе источника оставшиеся наборы этого источника
    не запрашиваются, второй источник загружается полностью.
    Время можно передать аргументом, чтобы тесты не зависели
    от текущего часа.
    """
    result = DownloadResult()
    timestamp = current_timestamp()
    current_time = now or datetime.now(UTC)
    for group, (folder, extension) in CELESTRAK_DATASETS.items():
        code = dataset_code(folder)
        reason = skip_reason(code, current_time, last_fetches.get(code))
        if reason:
            result.skipped[folder] = reason
            continue
        file_path = make_dataset_path(
            data_directory, folder, extension, timestamp
        )
        try:
            body = celestrak_client.fetch_gp(group)
        except SourceStopped as error:
            result.errors["celestrak"] = str(error)
            break
        result.datasets[folder] = save_original(body, file_path)
        upload_snapshot(result, uploader, folder, file_path, data_directory)
    for api_class, (folder, extension) in SPACE_TRACK_DATASETS.items():
        code = dataset_code(folder)
        reason = skip_reason(code, current_time, last_fetches.get(code))
        if reason:
            result.skipped[folder] = reason
            continue
        file_path = make_dataset_path(
            data_directory, folder, extension, timestamp
        )
        try:
            body = space_track_client.fetch(api_class)
        except SourceStopped as error:
            result.errors["space_track"] = str(error)
            break
        result.datasets[folder] = save_original(body, file_path)
        upload_snapshot(result, uploader, folder, file_path, data_directory)
    return result


def dataset_code(folder: str) -> str:
    """Код набора из папки: space_track/satcat -> satcat."""
    return folder.rsplit("/", 1)[-1]


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
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")


def upload_snapshot(
    result: DownloadResult,
    uploader: SnapshotUploader | None,
    folder: str,
    file_path: Path,
    data_directory: Path,
) -> None:
    """Выгружает снимок в Bronze, если загрузчик передан."""
    if uploader is None:
        return
    try:
        result.uploads[folder] = uploader.upload(file_path, data_directory)
    except UploadError as error:
        result.errors[f"upload:{folder}"] = str(error)
