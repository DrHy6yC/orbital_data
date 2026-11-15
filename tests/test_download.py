from collections.abc import Callable

import httpx
import pytest

from orbital_data.collectors.celestrak import CelesTrakClient
from orbital_data.collectors.download import download_datasets
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


def test_downloads_five_datasets_in_order() -> None:
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
    result = download_datasets(celestrak, space_track)

    assert list(result.datasets) == [
        "celestrak_stations",
        "celestrak_active",
        "space_track_gp",
        "space_track_satcat",
        "space_track_decay",
    ]
    assert result.datasets["celestrak_stations"] == CSV_BODY
    assert result.datasets["space_track_decay"] == JSON_BODY
    assert result.errors == {}
    assert calls == [
        "STATIONS",
        "ACTIVE",
        "login",
        f"{QUERY_PREFIX}/gp/format/json",
        f"{QUERY_PREFIX}/satcat/format/json",
        f"{QUERY_PREFIX}/decay/format/json",
    ]


def test_keeps_space_track_when_celestrak_fails() -> None:
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
    result = download_datasets(celestrak, space_track)

    assert list(result.datasets) == [
        "celestrak_stations",
        "space_track_gp",
        "space_track_satcat",
        "space_track_decay",
    ]
    assert list(result.errors) == ["celestrak"]
    assert "403" in result.errors["celestrak"]
    assert calls == [
        "STATIONS",
        "ACTIVE",
        "login",
        f"{QUERY_PREFIX}/gp/format/json",
        f"{QUERY_PREFIX}/satcat/format/json",
        f"{QUERY_PREFIX}/decay/format/json",
    ]


def test_keeps_celestrak_when_space_track_fails() -> None:
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
    result = download_datasets(celestrak, space_track)

    assert list(result.datasets) == [
        "celestrak_stations",
        "celestrak_active",
        "space_track_gp",
    ]
    assert list(result.errors) == ["space_track"]
    assert not any(
        path.endswith("/decay/format/json") for path in calls
    )
