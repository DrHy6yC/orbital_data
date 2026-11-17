from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from orbital_data.s3_access import read_settings
from orbital_data.source_snapshots.upload import (
    BUCKET,
    SnapshotUploader,
    UploadError,
    make_key,
)

FILE_NAME = "2026-11-15T10-10-00Z.json"


class FakeClient:
    """Подменяет клиент boto3: запоминает выгрузки или падает."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.uploads: list[tuple[str, str]] = []

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        if self.error is not None:
            raise self.error
        self.uploads.append((bucket, key))


def make_file(data_directory: Path) -> Path:
    """Создаёт файл снимка внутри каталога данных."""
    file_path = data_directory / "space_track" / "gp" / FILE_NAME
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b'[{"NORAD_CAT_ID": "25544"}]')
    return file_path


def test_builds_key_from_local_path(tmp_path: Path) -> None:
    file_path = make_file(tmp_path)

    key = make_key(file_path, tmp_path)

    assert key == f"space_track/gp/{FILE_NAME}"


def test_refuses_file_outside_data_directory(tmp_path: Path) -> None:
    data_directory = tmp_path / "data"
    outside_path = tmp_path / "other" / FILE_NAME
    outside_path.parent.mkdir()
    outside_path.write_bytes(b"[]")

    with pytest.raises(UploadError):
        make_key(outside_path, data_directory)


def test_uploads_to_bronze(tmp_path: Path) -> None:
    file_path = make_file(tmp_path)
    client = FakeClient()
    uploader = SnapshotUploader(client=client)

    key = uploader.upload(file_path, tmp_path)

    assert BUCKET == "bronze"
    assert key == f"space_track/gp/{FILE_NAME}"
    assert client.uploads == [(BUCKET, key)]


def test_reports_upload_error(tmp_path: Path) -> None:
    file_path = make_file(tmp_path)
    error = ClientError(
        {"Error": {"Code": "500", "Message": "нет связи"}},
        "PutObject",
    )
    uploader = SnapshotUploader(client=FakeClient(error))

    with pytest.raises(UploadError):
        uploader.upload(file_path, tmp_path)


def test_read_settings_needs_every_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("S3_RUSTFS_HOST", "localhost")
    monkeypatch.setenv("S3_RUSTFS_PORT", "9000")
    monkeypatch.setenv("S3_RUSTFS_ACCESS_KEY", "orbital")
    monkeypatch.delenv("S3_RUSTFS_SECRET_KEY", raising=False)

    with pytest.raises(UploadError):
        read_settings("RUSTFS")


def test_read_settings_checks_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("S3_RUSTFS_HOST", "localhost")
    monkeypatch.setenv("S3_RUSTFS_PORT", "девять тысяч")
    monkeypatch.setenv("S3_RUSTFS_ACCESS_KEY", "orbital")
    monkeypatch.setenv("S3_RUSTFS_SECRET_KEY", "secret")

    with pytest.raises(UploadError):
        read_settings("RUSTFS")
