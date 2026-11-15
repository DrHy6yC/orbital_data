"""Проверка подключения: по одному запросу к CelesTrak и Space-Track.

Запуск из корня проекта (учётные данные берутся из .env):
    uv run --env-file .env python utils/check_connection.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orbital_data.collectors.celestrak import CelesTrakClient  # noqa: E402
from orbital_data.collectors.space_track import SpaceTrackClient  # noqa: E402


def main() -> None:
    with CelesTrakClient() as celestrak:
        body = celestrak.fetch_gp("STATIONS")
        print(f"CelesTrak: {len(body)} байт")
    with SpaceTrackClient.from_env() as space_track:
        body = space_track.fetch("gp", "NORAD_CAT_ID/25544")
        print(f"Space-Track: {len(body)} байт")


if __name__ == "__main__":
    main()
