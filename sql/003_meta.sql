-- Копии снимков по хранилищам.
CREATE TABLE orbital.snapshot_copies (
    copy_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id integer NOT NULL
        REFERENCES orbital.snapshots (snapshot_id),
    storage text NOT NULL
        CHECK (storage IN ('rustfs', 'minio', 'yandex')),
    object_key text NOT NULL,
    file_size_bytes bigint NOT NULL CHECK (file_size_bytes > 0),
    etag text,
    status text NOT NULL CHECK (status IN ('ok', 'failed')),
    copied_at timestamptz NOT NULL,
    UNIQUE (snapshot_id, storage)
);

CREATE INDEX snapshot_copies_storage_key_index
    ON orbital.snapshot_copies (storage, object_key);

-- Прогон открывается до получения результата, статус ставится
-- при завершении.
ALTER TABLE orbital.runs ALTER COLUMN status DROP NOT NULL;