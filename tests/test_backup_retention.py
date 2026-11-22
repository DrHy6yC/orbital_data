from datetime import UTC, datetime

from orbital_data.backup_retention import (
    cloud_bronze_copies,
    expired_keys,
    parse_key,
    snapshot_key,
)

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


def test_snapshot_key_strips_prefix_and_suffix() -> None:
    key = "bronze/space_track/gp/2026-11-17T12-25-52Z.json.gz"

    assert snapshot_key(key) == "space_track/gp/2026-11-17T12-25-52Z.json"


def test_snapshot_key_keeps_key_without_suffix() -> None:
    key = "bronze/celestrak/gp_stations/2026-11-17T12-25-52Z.csv"

    assert (
        snapshot_key(key) == "celestrak/gp_stations/2026-11-17T12-25-52Z.csv"
    )


def test_snapshot_key_does_not_touch_dump_prefix() -> None:
    key = "postgres/orbital_data_2026-11-19T08-38-59Z.sql.gz"

    assert (
        snapshot_key(key) == "postgres/orbital_data_2026-11-19T08-38-59Z.sql"
    )


def test_cloud_copies_keep_bronze_objects() -> None:
    objects = {
        "bronze/celestrak/gp_stations/2026-11-17T17-55-54Z.csv.gz": 995,
        "bronze/space_track/gp/2026-11-17T17-55-54Z.json.gz": 11_650_000,
    }

    copies = cloud_bronze_copies(objects, set())

    assert copies == {
        "celestrak/gp_stations/2026-11-17T17-55-54Z.csv": (
            "bronze/celestrak/gp_stations/2026-11-17T17-55-54Z.csv.gz",
            995,
        ),
        "space_track/gp/2026-11-17T17-55-54Z.json": (
            "bronze/space_track/gp/2026-11-17T17-55-54Z.json.gz",
            11_650_000,
        ),
    }


def test_cloud_copies_skip_expired_objects() -> None:
    objects = {
        "bronze/space_track/gp/2026-11-10T10-00-00Z.json.gz": 100,
        "bronze/space_track/gp/2026-11-17T17-00-00Z.json.gz": 100,
    }
    expired = {"bronze/space_track/gp/2026-11-10T10-00-00Z.json.gz"}

    copies = cloud_bronze_copies(objects, expired)

    assert list(copies) == ["space_track/gp/2026-11-17T17-00-00Z.json"]


def test_cloud_copies_skip_dumps() -> None:
    objects = {"postgres/orbital_data_2026-11-19T08-38-59Z.sql.gz": 10}

    assert cloud_bronze_copies(objects, set()) == {}


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


def test_keeps_newest_snapshot_when_loading_stopped() -> None:
    objects = {
        "bronze/space_track/gp/2026-11-10T10-00-00Z.json.gz": 100,
        "bronze/space_track/gp/2026-11-12T10-00-00Z.json.gz": 100,
    }

    plan = expired_keys(objects, {"gp": 2}, NOW)

    assert plan.expired == [
        "bronze/space_track/gp/2026-11-10T10-00-00Z.json.gz"
    ]
    assert plan.unknown == []


def test_keeps_only_snapshot_of_dataset() -> None:
    objects = {"bronze/space_track/decay/2026-10-01T10-00-00Z.json.gz": 100}

    plan = expired_keys(objects, {"decay": 14}, NOW)

    assert plan.expired == []
    assert plan.unknown == []
