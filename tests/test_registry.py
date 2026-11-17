from datetime import UTC, datetime
from pathlib import Path

import pytest

from orbital_data.source_snapshots.registry import (
    RegistryError,
    define_status,
    file_checksum,
    parse_fetched_at,
    split_folder,
)


def test_splits_folder_into_source_and_dataset() -> None:
    assert split_folder("space_track/gp") == ("space_track", "gp")


def test_rejects_folder_without_dataset() -> None:
    with pytest.raises(RegistryError):
        split_folder("gp")


def test_parses_time_from_file_name(tmp_path: Path) -> None:
    file_path = tmp_path / "2026-11-17T12-25-52Z.json"
    file_path.write_bytes(b"[]")

    moment = parse_fetched_at(file_path)

    assert moment == datetime(2026, 11, 17, 12, 25, 52, tzinfo=UTC)


def test_rejects_file_name_without_time(tmp_path: Path) -> None:
    with pytest.raises(RegistryError):
        parse_fetched_at(tmp_path / "snapshot.json")


def test_checksum_matches_known_value(tmp_path: Path) -> None:
    file_path = tmp_path / "snapshot.json"
    file_path.write_bytes(b"orbital")

    assert file_checksum(file_path) == (
        "a24e63c5bef69d676ddf46c3f918c107ce64dc7846b55952f3407b9276fa3bcf"
    )


@pytest.mark.parametrize(
    ("saved", "errors", "expected"),
    [
        (5, 0, "success"),
        (3, 2, "partial"),
        (0, 2, "failed"),
    ],
)
def test_defines_status(saved: int, errors: int, expected: str) -> None:
    assert define_status(saved, errors) == expected
