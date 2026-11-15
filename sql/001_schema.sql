CREATE SCHEMA IF NOT EXISTS orbital;

CREATE TABLE orbital.sources (
    source_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE,
    title text NOT NULL,
    base_url text NOT NULL
);

CREATE TABLE orbital.datasets (
    dataset_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id integer NOT NULL REFERENCES orbital.sources (source_id),
    code text NOT NULL,
    title text NOT NULL,
    file_format text NOT NULL,
    UNIQUE (source_id, code)
);

CREATE TABLE orbital.runs (
    run_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    status text NOT NULL CHECK (status IN ('success', 'partial', 'failed')),
    error_message text
);

CREATE TABLE orbital.snapshots (
    snapshot_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id integer NOT NULL REFERENCES orbital.runs (run_id),
    dataset_id integer NOT NULL REFERENCES orbital.datasets (dataset_id),
    fetched_at timestamptz NOT NULL,
    file_name text NOT NULL,
    file_size_bytes bigint NOT NULL CHECK (file_size_bytes > 0),
    checksum_sha256 char(64) NOT NULL,
    storage_path text NOT NULL,
    UNIQUE (dataset_id, fetched_at)
);
