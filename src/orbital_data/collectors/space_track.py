"""Клиент Space-Track: вход по учётной записи и запросы в рамках сессии."""

import os
import time
from collections.abc import Callable

import httpx

from orbital_data.collectors.errors import SourceStopped

BASE_URL = "https://www.space-track.org"
LOGIN_URL = f"{BASE_URL}/ajaxauth/login"
QUERY_URL = f"{BASE_URL}/basicspacedata/query"
USER_AGENT = "orbital-data/0.1 (learning project)"
TIMEOUT_SECONDS = 60.0
MAX_ATTEMPTS = 3
DEFAULT_PAUSE_SECONDS = 60.0


def _pause(response: httpx.Response) -> float:
    value = response.headers.get("Retry-After", "")
    return float(value) if value.isdigit() else DEFAULT_PAUSE_SECONDS


class SpaceTrackClient:
    def __init__(
        self,
        identity: str,
        password: str,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._identity = identity
        self._password = password
        self._client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS
        )
        self._sleep = sleep
        self._logged_in = False

    @classmethod
    def from_env(cls) -> "SpaceTrackClient":
        try:
            return cls(os.environ["SPACETRACK_USER"], os.environ["SPACETRACK_PASSWORD"])
        except KeyError as error:
            raise RuntimeError(f"Не задана переменная окружения {error.args[0]}") from error

    def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            last = attempt == MAX_ATTEMPTS
            try:
                response = self._client.request(method, url, **kwargs)
            except httpx.TransportError as error:  # тайм-аут, сбой соединения
                if last:
                    raise SourceStopped(f"Space-Track: сетевая ошибка {error!r}") from error
                self._sleep(DEFAULT_PAUSE_SECONDS)
                continue
            status = response.status_code
            if status == 429 or status >= 500:
                if last:
                    raise SourceStopped(f"Space-Track: HTTP {status} после {attempt} попыток")
                self._sleep(_pause(response))
                continue
            if status != 200:  # в том числе 401 и 403
                raise SourceStopped(f"Space-Track: HTTP {status}, запросы прекращены")
            return response
        raise SourceStopped("Space-Track: попытки исчерпаны")

    def login(self) -> None:
        response = self._send(
            "POST", LOGIN_URL, data={"identity": self._identity, "password": self._password}
        )
        if "Failed" in response.text:  # неверные данные: ответ 200 с телом о неудаче
            raise SourceStopped("Space-Track: учётные данные отклонены")
        self._logged_in = True

    def fetch(self, api_class: str, *conditions: str, fmt: str = "json") -> bytes:
        """Запрос класса API, например fetch("gp", "NORAD_CAT_ID/25544")."""
        if not self._logged_in:
            self.login()
        url = "/".join([QUERY_URL, "class", api_class.lower(), *conditions, "format", fmt])
        body = self._send("GET", url).content
        if not body.strip():
            raise SourceStopped("Space-Track: пустое тело ответа")
        return body

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SpaceTrackClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
