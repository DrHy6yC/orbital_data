"""Правила окон запросов к источникам.

Окно проверяется до запроса: если набор получен слишком недавно,
запрос не выполняется. Время последнего снимка приходит аргументом,
модуль в базу и в сеть не ходит.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

HOUR = timedelta(hours=1)


@dataclass(frozen=True)
class Window:
    """Как часто можно запрашивать набор."""

    interval: timedelta
    earliest_hour: int | None = None


WINDOWS = {
    "gp": Window(interval=HOUR),
    "gp_active": Window(interval=2 * HOUR),
    "gp_stations": Window(interval=2 * HOUR),
    "satcat": Window(interval=24 * HOUR, earliest_hour=17),
    "decay": Window(interval=24 * HOUR),
}


def skip_reason(
    dataset: str, now: datetime, last_fetch: datetime | None
) -> str | None:
    """Возвращает причину пропуска набора или None, если можно грузить."""
    window = WINDOWS.get(dataset)
    if window is None:
        return None
    if window.earliest_hour is not None:
        if now.hour < window.earliest_hour:
            return (
                f"источник обновляет набор не раньше "
                f"{window.earliest_hour}:00 UTC"
            )
    if last_fetch is not None:
        passed = now - last_fetch
        if passed < window.interval:
            return (
                f"прошло {format_duration(passed)} "
                f"при окне {format_duration(window.interval)}"
            )
    return None


def format_duration(delta: timedelta) -> str:
    """Пишет длительность коротко: 45 мин, 3 ч, 1 сут 4 ч."""
    total_minutes = int(delta.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days} сут {hours} ч" if hours else f"{days} сут"
    if hours:
        return f"{hours} ч {minutes} мин" if minutes else f"{hours} ч"
    if minutes:
        return f"{minutes} мин"
    return "меньше минуты"
