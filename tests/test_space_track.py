import httpx
import pytest

from orbital_data.collectors.errors import SourceStopped
from orbital_data.collectors.space_track import SpaceTrackClient

LOGIN_PATH = "/ajaxauth/login"
GP_PATH = "/basicspacedata/query/class/gp/NORAD_CAT_ID/25544/format/json"
BODY = b'[{"NORAD_CAT_ID": "25544"}]'


def make_client(handler, sleeps: list | None = None) -> SpaceTrackClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    pauses = [] if sleeps is None else sleeps
    return SpaceTrackClient("user", "secret", client=http, sleep=pauses.append)


def test_logs_in_once_and_fetches() -> None:
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == LOGIN_PATH:
            return httpx.Response(200, text="")
        return httpx.Response(200, content=BODY)

    client = make_client(handler)
    assert client.fetch("gp", "NORAD_CAT_ID/25544") == BODY
    client.fetch("gp", "NORAD_CAT_ID/25544")
    assert paths == [LOGIN_PATH, GP_PATH, GP_PATH]


def test_stops_on_rejected_credentials() -> None:
    client = make_client(
        lambda request: httpx.Response(200, json={"Login": "Failed"})
    )
    with pytest.raises(SourceStopped):
        client.login()


def test_stops_on_403_without_retry() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == LOGIN_PATH:
            return httpx.Response(200, text="")
        return httpx.Response(403)

    with pytest.raises(SourceStopped):
        make_client(handler).fetch("gp", "NORAD_CAT_ID/25544")
    assert calls.count(GP_PATH) == 1


def test_waits_retry_after_on_429_then_succeeds() -> None:
    answers = iter(
        [
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, content=BODY),
        ]
    )
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == LOGIN_PATH:
            return httpx.Response(200, text="")
        return next(answers)

    client = make_client(handler, sleeps)
    assert client.fetch("gp", "NORAD_CAT_ID/25544") == BODY
    assert sleeps == [7.0]


def test_gives_up_after_three_server_errors() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == LOGIN_PATH:
            return httpx.Response(200, text="")
        return httpx.Response(503)

    with pytest.raises(SourceStopped):
        make_client(handler).fetch("gp", "NORAD_CAT_ID/25544")
    assert calls.count(GP_PATH) == 3
