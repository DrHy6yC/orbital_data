import re
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from orbital_data.collectors.celestrak import CelesTrakClient
from orbital_data.collectors.download import (
    current_timestamp,
    download_datasets,
    make_dataset_path,
)
from orbital_data.collectors.space_track import SpaceTrackClient

CSV_BODY = b"OBJECT_NAME,OBJECT_ID\nISS (ZARYA),1998-067A\n"
JSON_BODY = b'[{"NORAD_CAT_ID": "25544"}]'
LOGIN_PATH = "/ajaxauth/login"
QUERY_PREFIX = "/basicspacedata/query/class"


def skip_pause(pause: float) -> None:
    """Заменяет паузу между попытками: в тестах ждать не нужно."""


def make_clients(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[CelesTrakClient, SpaceTrackClient]:
    """Создаёт оба клиента на одном поддельном транспорте."""
    transport = httpx.MockTransport(handler)
    celestrak = CelesTrakClient(httpx.Client(transport=transport))
    space_track = SpaceTrackClient(
        "user",
        "secret",
        client=httpx.Client(transport=transport),
        sleep=skip_pause,
    )
    return celestrak, space_track


def test_downloads_and_saves_five_datasets(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "celestrak.org":
            calls.append(request.url.params["GROUP"])
            return httpx.Response(200, content=CSV_BODY)
        if request.url.path == LOGIN_PATH:
            calls.append("login")
            return httpx.Response(200, text="")
        calls.append(request.url.path)
        return httpx.Response(200, content=JSON_BODY)

    celestrak, space_track = make_clients(handler)
    result = download_datasets(celestrak, space_track, tmp_path)

    assert list(result.datasets) == [
        "celestrak/gp_stations",
        "celestrak/gp_active",
        "space_track/gp",
        "space_track/satcat",
        "space_track/decay",
    ]
    assert result.errors == {}
    assert calls == [
        "STATIONS",
        "ACTIVE",
        "login",
        f"{QUERY_PREFIX}/gp/format/json",
        f"{QUERY_PREFIX}/satcat/format/json",
        f"{QUERY_PREFIX}/decay/format/json",
    ]
    stations_file = result.datasets["celestrak/gp_stations"]
    assert stations_file.parent.name == "gp_stations"
    assert stations_file.parent.parent.name == "celestrak"
    assert stations_file.suffix == ".csv"
    assert stations_file.read_bytes() == CSV_BODY
    decay_file = result.datasets["space_track/decay"]
    assert decay_file.suffix == ".json"
    assert decay_file.read_bytes() == JSON_BODY


def test_keeps_space_track_when_celestrak_fails(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "celestrak.org":
            group = request.url.params["GROUP"]
            calls.append(group)
            if group == "ACTIVE":
                return httpx.Response(403)
            return httpx.Response(200, content=CSV_BODY)
        if request.url.path == LOGIN_PATH:
            calls.append("login")
            return httpx.Response(200, text="")
        calls.append(request.url.path)
        return httpx.Response(200, content=JSON_BODY)

    celestrak, space_track = make_clients(handler)
    result = download_datasets(celestrak, space_track, tmp_path)

    assert list(result.datasets) == [
        "celestrak/gp_stations",
        "space_track/gp",
        "space_track/satcat",
        "space_track/decay",
    ]
    assert list(result.errors) == ["celestrak"]
    assert "403" in result.errors["celestrak"]
    stations_file = result.datasets["celestrak/gp_stations"]
    assert stations_file.read_bytes() == CSV_BODY
    assert not (tmp_path / "celestrak" / "gp_active").exists()


def test_keeps_celestrak_when_space_track_fails(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "celestrak.org":
            calls.append(request.url.params["GROUP"])
            return httpx.Response(200, content=CSV_BODY)
        if request.url.path == LOGIN_PATH:
            return httpx.Response(200, text="")
        calls.append(request.url.path)
        if request.url.path.endswith("/satcat/format/json"):
            return httpx.Response(503)
        return httpx.Response(200, content=JSON_BODY)

    celestrak, space_track = make_clients(handler)
    result = download_datasets(celestrak, space_track, tmp_path)

    assert list(result.datasets) == [
        "celestrak/gp_stations",
        "celestrak/gp_active",
        "space_track/gp",
    ]
    assert list(result.errors) == ["space_track"]
    assert not (tmp_path / "space_track" / "decay").exists()


def test_builds_path_from_timestamp(tmp_path: Path) -> None:
    file_path = make_dataset_path(
        tmp_path, "space_track/gp", "json", "2026-11-15T10-10-00Z"
    )

    assert file_path == (
        tmp_path / "space_track" / "gp" / "2026-11-15T10-10-00Z.json"
    )


def test_timestamp_has_no_colons() -> None:
    timestamp = current_timestamp()

    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z", timestamp
    )