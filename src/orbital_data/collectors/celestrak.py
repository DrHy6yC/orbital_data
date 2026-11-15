"""Клиент CelesTrak: открытый API, без авторизации и без повторных попыток."""

import httpx

from orbital_data.collectors.errors import SourceStopped

BASE_URL = "https://celestrak.org/NORAD/elements/gp.php"
USER_AGENT = "orbital-data/0.1 (learning project)"
TIMEOUT_SECONDS = 60.0
ERROR_PREFIXES = ("invalid query", "no gp data found")


class CelesTrakClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,
        )

    def fetch_gp(self, group: str, fmt: str = "CSV") -> bytes:
        """Один запрос GP по группе. Любой ответ, кроме HTTP 200, останавливает работу."""
        try:
            response = self._client.get(BASE_URL, params={"GROUP": group, "FORMAT": fmt})
        except httpx.HTTPError as error:
            raise SourceStopped(f"CelesTrak: сетевая ошибка {error!r}") from error
        if response.status_code != 200:
            raise SourceStopped(f"CelesTrak: HTTP {response.status_code}, запросы прекращены")
        body = response.content
        head = body[:200].decode("utf-8", errors="replace").strip().lower()
        if not head:
            raise SourceStopped("CelesTrak: пустое тело ответа")
        if head.startswith(ERROR_PREFIXES):
            raise SourceStopped(f"CelesTrak: ответ похож на ошибку: {head[:80]}")
        return body

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "CelesTrakClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
