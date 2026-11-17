from datetime import UTC, datetime, timedelta

from orbital_data.collectors.windows import format_duration, skip_reason

NOW = datetime(2026, 11, 18, 18, 0, 0, tzinfo=UTC)


def test_allows_first_request() -> None:
    assert skip_reason("gp", NOW, None) is None


def test_allows_dataset_outside_window() -> None:
    last = NOW - timedelta(minutes=61)

    assert skip_reason("gp", NOW, last) is None


def test_skips_dataset_inside_window() -> None:
    last = NOW - timedelta(minutes=30)

    assert skip_reason("gp", NOW, last) == "прошло 30 мин при окне 1 ч"


def test_skips_two_hour_dataset() -> None:
    last = NOW - timedelta(minutes=119)

    assert skip_reason("gp_active", NOW, last) is not None


def test_skips_daily_dataset() -> None:
    last = NOW - timedelta(hours=23)

    assert skip_reason("decay", NOW, last) == ("прошло 23 ч при окне 1 сут")


def test_allows_daily_dataset_after_a_day() -> None:
    last = NOW - timedelta(hours=25)

    assert skip_reason("decay", NOW, last) is None


def test_skips_satcat_before_17_utc() -> None:
    morning = NOW.replace(hour=10)

    assert skip_reason("satcat", morning, None) == (
        "источник обновляет набор не раньше 17:00 UTC"
    )


def test_skips_satcat_fetched_recently() -> None:
    last = NOW - timedelta(hours=2)

    assert skip_reason("satcat", NOW, last) is not None


def test_allows_satcat_after_17_utc() -> None:
    last = NOW - timedelta(hours=25)

    assert skip_reason("satcat", NOW, last) is None


def test_allows_dataset_without_rule() -> None:
    assert skip_reason("research", NOW, NOW) is None


def test_formats_durations() -> None:
    assert format_duration(timedelta(minutes=45)) == "45 мин"
    assert format_duration(timedelta(hours=2)) == "2 ч"
    assert format_duration(timedelta(days=1, hours=4)) == "1 сут 4 ч"
    assert format_duration(timedelta(seconds=20)) == "меньше минуты"
