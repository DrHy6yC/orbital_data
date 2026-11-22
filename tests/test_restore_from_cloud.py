import gzip
import hashlib
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from orbital_data.cloud_restore import (
    BRONZE_BUCKET,
    dataset_of,
    newest_keys,
    parse_dataset,
    restore_object,
)

PAYLOAD = b"norad_id,epoch\n25544,2026-11-17\n"
CLOUD_KEY = "bronze/celestrak/gp_stations/2026-11-17T17-55-54Z.csv.gz"
STORAGE_KEY = "celestrak/gp_stations/2026-11-17T17-55-54Z.csv"
CLOUD_BUCKET = "cloud-backup"


class FakeCloud:
    """Облачный бакет в памяти с методами boto3 для восстановления."""

    def __init__(self, body: bytes, metadata: dict[str, str]) -> None:
        self.body = body
        self.metadata = metadata
        self.requested_buckets: list[str] = []

    def head_object(self, Bucket: str, Key: str) -> dict:
        self.requested_buckets.append(Bucket)
        return {"ContentLength": len(self.body), "Metadata": self.metadata}

    def download_file(
        self,
        bucket: str,
        key: str,
        target_path: str,
        Config: object | None = None,
    ) -> None:
        self.requested_buckets.append(bucket)
        Path(target_path).write_bytes(self.body)


class FakeStorage:
    """Хранилище в памяти: бакеты, объекты и счётчик загрузок."""

    def __init__(self) -> None:
        self.buckets: dict[str, dict[str, bytes]] = {}
        self.uploads = 0

    def head_bucket(self, Bucket: str) -> None:
        if Bucket not in self.buckets:
            raise ClientError({"Error": {"Code": "404"}}, "HeadBucket")

    def create_bucket(self, Bucket: str) -> None:
        self.buckets[Bucket] = {}

    def head_object(self, Bucket: str, Key: str) -> dict:
        objects = self.buckets.get(Bucket, {})
        if Key not in objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "HeadObject")
        return {"ContentLength": len(objects[Key])}

    def upload_fileobj(self, body, Bucket: str, Key: str) -> None:
        self.buckets[Bucket][Key] = body.read()
        self.uploads += 1


def checksum_of(body: bytes) -> str:
    """Считает sha256 так же, как загрузчик и проверка."""
    return hashlib.sha256(body).hexdigest()


def make_cloud(metadata_checksum: str | None = None) -> FakeCloud:
    """Создаёт облако с одним сжатым объектом и метаданными."""
    digest = (
        checksum_of(PAYLOAD)
        if metadata_checksum is None
        else metadata_checksum
    )
    return FakeCloud(gzip.compress(PAYLOAD), {"Sha256": digest})


def test_parse_dataset_keeps_value() -> None:
    assert parse_dataset(" space_track/gp ") == "space_track/gp"


@pytest.mark.parametrize("value", ["", "gp", "space_track/", "/gp", "a/b/c"])
def test_parse_dataset_rejects_wrong_format(value: str) -> None:
    with pytest.raises(ValueError):
        parse_dataset(value)


def test_dataset_of_returns_source_and_dataset() -> None:
    assert dataset_of(CLOUD_KEY) == "celestrak/gp_stations"


def test_dataset_of_ignores_foreign_key() -> None:
    assert dataset_of("postgres/orbital_data_2026-11-19Z.sql.gz") is None


def test_newest_keys_keeps_last_snapshot_of_each_dataset() -> None:
    cloud_keys = [
        "bronze/celestrak/gp_stations/2026-11-17T12-25-52Z.csv.gz",
        "bronze/celestrak/gp_stations/2026-11-17T17-55-54Z.csv.gz",
        "bronze/space_track/gp/2026-11-17T14-54-50Z.json.gz",
    ]

    assert newest_keys(cloud_keys, None) == [
        "bronze/celestrak/gp_stations/2026-11-17T17-55-54Z.csv.gz",
        "bronze/space_track/gp/2026-11-17T14-54-50Z.json.gz",
    ]


def test_newest_keys_keeps_two_sources_with_same_dataset_code() -> None:
    cloud_keys = [
        "bronze/celestrak/gp/2026-11-17T12-25-52Z.csv.gz",
        "bronze/space_track/gp/2026-11-17T12-25-52Z.json.gz",
    ]

    assert len(newest_keys(cloud_keys, None)) == 2


def test_newest_keys_filters_by_dataset() -> None:
    cloud_keys = [
        "bronze/celestrak/gp_active/2026-11-17T17-55-54Z.csv.gz",
        "bronze/space_track/gp/2026-11-17T17-55-54Z.json.gz",
    ]

    assert newest_keys(cloud_keys, "space_track/gp") == [
        "bronze/space_track/gp/2026-11-17T17-55-54Z.json.gz"
    ]


def test_newest_keys_ignores_dumps() -> None:
    cloud_keys = ["postgres/orbital_data_2026-11-19T08-38-59Z.sql.gz"]

    assert newest_keys(cloud_keys, None) == []


def test_restore_object_uploads_and_returns_size(tmp_path: Path) -> None:
    storage = FakeStorage()

    size = restore_object(
        make_cloud(), storage, CLOUD_BUCKET, CLOUD_KEY, tmp_path, {}
    )

    assert size == len(PAYLOAD)
    assert storage.buckets[BRONZE_BUCKET][STORAGE_KEY] == PAYLOAD


def test_restore_object_uses_cloud_bucket_only_for_cloud(
    tmp_path: Path,
) -> None:
    cloud = make_cloud()
    storage = FakeStorage()

    restore_object(cloud, storage, CLOUD_BUCKET, CLOUD_KEY, tmp_path, {})

    assert set(cloud.requested_buckets) == {CLOUD_BUCKET}
    assert list(storage.buckets) == [BRONZE_BUCKET]


def test_restore_object_rejects_metadata_mismatch(tmp_path: Path) -> None:
    storage = FakeStorage()

    size = restore_object(
        make_cloud("0" * 64),
        storage,
        CLOUD_BUCKET,
        CLOUD_KEY,
        tmp_path,
        {},
    )

    assert size is None
    assert storage.buckets == {}


def test_restore_object_rejects_database_mismatch(tmp_path: Path) -> None:
    storage = FakeStorage()
    checksums = {STORAGE_KEY: "0" * 64}

    size = restore_object(
        make_cloud(),
        storage,
        CLOUD_BUCKET,
        CLOUD_KEY,
        tmp_path,
        checksums,
    )

    assert size is None
    assert storage.buckets == {}


def test_restore_object_skips_existing_object(tmp_path: Path) -> None:
    storage = FakeStorage()
    storage.buckets[BRONZE_BUCKET] = {STORAGE_KEY: PAYLOAD}

    size = restore_object(
        make_cloud(), storage, CLOUD_BUCKET, CLOUD_KEY, tmp_path, {}
    )

    assert size == len(PAYLOAD)
    assert storage.uploads == 0
