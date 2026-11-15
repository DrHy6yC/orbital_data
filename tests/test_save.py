from pathlib import Path

import pytest

from orbital_data.source_snapshots.save import save_original

FILE_NAME = "2026-11-15T10-10-00Z.csv"


def test_creates_directories_and_writes_body(tmp_path: Path) -> None:
    file_path = tmp_path / "celestrak" / "gp_stations" / FILE_NAME

    saved_path = save_original(b"OBJECT_NAME\nISS\n", file_path)

    assert saved_path == file_path
    assert file_path.read_bytes() == b"OBJECT_NAME\nISS\n"
    assert not file_path.with_name(file_path.name + ".part").exists()


def test_refuses_to_overwrite_existing_file(tmp_path: Path) -> None:
    file_path = tmp_path / FILE_NAME
    file_path.write_bytes(b"old")

    with pytest.raises(FileExistsError):
        save_original(b"new", file_path)

    assert file_path.read_bytes() == b"old"


def test_refuses_empty_body(tmp_path: Path) -> None:
    file_path = tmp_path / FILE_NAME

    with pytest.raises(ValueError):
        save_original(b"", file_path)

    assert not file_path.exists()
