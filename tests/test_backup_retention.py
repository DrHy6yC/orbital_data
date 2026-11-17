from datetime import UTC, datetime

from orbital_data.backup_retention import expired_keys, parse_key

NOW = datetime(2026, 11, 17, 18, 0, 0, tzinfo=UTC)


def test_parses_cloud_key() -> None:
    key = "bronze/space_track/gp/2026-11-17T12-25-52Z.json.gz"

    assert parse_key(key) == (
        "gp",
        datetime(2026, 11, 17, 12, 25, 52, tzinfo=UTC),
    )


def test_ignores_key_outside_bronze() -> None:
    key = "postgres/orbital_data_2026-11-17T15-55-07Z.sql.gz"

    assert parse_key(key) is None


def test_ignores_key_with_extra_level() -> None:
    key = "bronze/research/celestrak/run/2026-11-17T12-25-52Z.csv.gz"

    assert parse_key(key) is None


def test_ignores_key_without_time() -> None:
    assert parse_key("bronze/space_track/gp/snapshot.json.gz") is None


def test_marks_old_snapshot_as_expired() -> None:
    objects = {
        "bronze/space_track/gp/2026-11-15T10-00-00Z.json.gz": 100,
        "bronze/space_track/gp/2026-11-17T17-00-00Z.json.gz": 100,
        "postgres/orbital_data_2026-11-10T10-00-00Z.sql.gz": 10,
    }

    plan = expired_keys(objects, {"gp": 2}, NOW)

    assert plan.expired == [
        "bronze/space_track/gp/2026-11-15T10-00-00Z.json.gz"
    ]
    assert plan.unknown == []


def test_keeps_dataset_without_window() -> None:
    objects = {"bronze/celestrak/gp_active/2026-11-01T10-00-00Z.csv.gz": 100}

    plan = expired_keys(objects, {"gp": 2}, NOW)

    assert plan.expired == []
    assert plan.unknown == [
        "bronze/celestrak/gp_active/2026-11-01T10-00-00Z.csv.gz"
    ]


def test_keeps_unparsable_bronze_key() -> None:
    plan = expired_keys({"bronze/broken.json.gz": 5}, {"gp": 2}, NOW)

    assert plan.expired == []
    assert plan.unknown == ["bronze/broken.json.gz"]
