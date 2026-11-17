import io

from botocore.exceptions import ClientError

from orbital_data.mirror import mirror_buckets


class FakeStorage:
    """Хранилище в памяти с методами boto3, которые нужно зеркалу.

    Имена аргументов совпадают с boto3, поэтому написаны как там.
    """

    def __init__(
        self, buckets: dict[str, dict[str, bytes]] | None = None
    ) -> None:
        self.buckets = buckets or {}
        self.fail_keys: set[str] = set()

    def head_bucket(self, Bucket: str) -> None:
        if Bucket not in self.buckets:
            raise ClientError({"Error": {"Code": "404"}}, "HeadBucket")

    def create_bucket(self, Bucket: str) -> None:
        self.buckets[Bucket] = {}

    def list_objects_v2(
        self, Bucket: str, ContinuationToken: str = ""
    ) -> dict:
        objects = self.buckets.get(Bucket, {})
        contents = [
            {"Key": key, "Size": len(body)}
            for key, body in sorted(objects.items())
        ]
        return {"Contents": contents, "IsTruncated": False}

    def head_object(self, Bucket: str, Key: str) -> dict:
        objects = self.buckets.get(Bucket, {})
        if Key not in objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "HeadObject")
        return {"ContentLength": len(objects[Key])}

    def get_object(self, Bucket: str, Key: str) -> dict:
        return {"Body": io.BytesIO(self.buckets[Bucket][Key])}

    def upload_fileobj(self, body: io.BytesIO, Bucket: str, Key: str) -> None:
        if Key in self.fail_keys:
            raise ClientError({"Error": {"Code": "500"}}, "PutObject")
        self.buckets[Bucket][Key] = body.read()


def make_source() -> FakeStorage:
    return FakeStorage(
        {
            "bronze": {
                "celestrak/gp_active/a.csv": b"one",
                "space_track/gp/a.json": b"two-two",
            },
            "silver": {},
        }
    )


def test_copies_missing_objects() -> None:
    target = FakeStorage()

    result = mirror_buckets(make_source(), target)

    assert result.copied == [
        "bronze/celestrak/gp_active/a.csv",
        "bronze/space_track/gp/a.json",
    ]
    assert result.skipped == []
    assert result.errors == {}
    assert target.buckets["bronze"]["space_track/gp/a.json"] == b"two-two"


def test_skips_objects_with_same_size() -> None:
    target = FakeStorage({"bronze": {"celestrak/gp_active/a.csv": b"one"}})

    result = mirror_buckets(make_source(), target)

    assert result.skipped == ["bronze/celestrak/gp_active/a.csv"]
    assert result.copied == ["bronze/space_track/gp/a.json"]


def test_rewrites_object_with_other_size() -> None:
    target = FakeStorage(
        {"bronze": {"celestrak/gp_active/a.csv": b"old-value"}}
    )

    result = mirror_buckets(make_source(), target, ("bronze",))

    assert "bronze/celestrak/gp_active/a.csv" in result.copied
    assert target.buckets["bronze"]["celestrak/gp_active/a.csv"] == b"one"


def test_dry_run_does_not_write() -> None:
    target = FakeStorage()

    result = mirror_buckets(make_source(), target, is_dry_run=True)

    assert result.dry_run is True
    assert len(result.copied) == 2
    assert target.buckets == {}


def test_creates_missing_bucket() -> None:
    target = FakeStorage()

    mirror_buckets(make_source(), target, ("bronze",))

    assert "bronze" in target.buckets


def test_records_error_and_continues() -> None:
    target = FakeStorage()
    target.fail_keys.add("celestrak/gp_active/a.csv")

    result = mirror_buckets(make_source(), target, ("bronze",))

    assert list(result.errors) == ["bronze/celestrak/gp_active/a.csv"]
    assert result.copied == ["bronze/space_track/gp/a.json"]
