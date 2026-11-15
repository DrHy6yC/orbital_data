"""Получение исходных ответов по выбранным наборам данных.

Наборы описаны в docs/data_sources/datasets.md. Источники независимы:
если один источник отказал, его оставшиеся наборы не запрашиваются,
а второй источник загружается полностью.
"""

from dataclasses import dataclass, field

from orbital_data.collectors.celestrak import CelesTrakClient
from orbital_data.collectors.errors import SourceStopped
from orbital_data.collectors.space_track import SpaceTrackClient

CELESTRAK_GROUPS = ("STATIONS", "ACTIVE")
SPACE_TRACK_CLASSES = ("gp", "satcat", "decay")


@dataclass
class DownloadResult:
    """Что загружено и на чём остановился каждый источник."""

    datasets: dict[str, bytes] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


def download_datasets(
    celestrak_client: CelesTrakClient,
    space_track_client: SpaceTrackClient,
) -> DownloadResult:
    """Загружает наборы по источникам, не прерываясь на отказе одного."""
    result = DownloadResult()
    for group in CELESTRAK_GROUPS:
        name = f"celestrak_{group.lower()}"
        try:
            result.datasets[name] = celestrak_client.fetch_gp(group)
        except SourceStopped as error:
            result.errors["celestrak"] = str(error)
            break
    for api_class in SPACE_TRACK_CLASSES:
        name = f"space_track_{api_class}"
        try:
            result.datasets[name] = space_track_client.fetch(api_class)
        except SourceStopped as error:
            result.errors["space_track"] = str(error)
            break
    return result
