import httpx
import pytest

from orbital_data.collectors.celestrak import CelesTrakClient
from orbital_data.collectors.errors import SourceStopped

CSV_BODY = b"OBJECT_NAME,OBJECT_ID\nISS (ZARYA),1998-067A\n"


def make_client(handler) -> CelesTrakClient:
    return CelesTrakClient(
        httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_returns_body_on_200() -> None:
    client = make_client(lambda request: httpx.Response(200, content=CSV_BODY))
    assert client.fetch_gp("STATIONS") == CSV_BODY


def test_sends_group_and_format() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params)
        return httpx.Response(200, content=CSV_BODY)

    make_client(handler).fetch_gp("STATIONS")
    assert seen[0]["GROUP"] == "STATIONS"
    assert seen[0]["FORMAT"] == "CSV"


@pytest.mark.parametrize("status", [301, 403, 404, 500])
def test_stops_on_non_200_without_retry(status: int) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status)

    with pytest.raises(SourceStopped):
        make_client(handler).fetch_gp("STATIONS")
    assert len(calls) == 1


@pytest.mark.parametrize(
    "body", [b"", b"  \n", b"Invalid query: x", b"No GP data found"]
)
def test_stops_on_empty_or_error_body(body: bytes) -> None:
    client = make_client(lambda request: httpx.Response(200, content=body))
    with pytest.raises(SourceStopped):
        client.fetch_gp("STATIONS")
