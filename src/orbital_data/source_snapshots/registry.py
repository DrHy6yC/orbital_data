"""Учёт прогонов, снимков и копий в PostgreSQL.

Записи ведутся после сохранения снимков: если база недоступна,
локальные файлы и выгрузка в Bronze не страдают.
"""

import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import psycopg

CHUNK_SIZE = 1024 * 1024
PRIMARY_STORAGE = "rustfs"


class RegistryError(RuntimeError):
    """Не удалось записать метаданные."""


def connect() -> psycopg.Connection:
    """Открывает соединение с базой метаданных по POSTGRES_*."""
    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        raise RegistryError("Не задан POSTGRES_PASSWORD, проверьте .env")
    connection = psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        user=os.environ.get("POSTGRES_USER", "orbital"),
        password=password,
        dbname=os.environ.get("POSTGRES_DB", "orbital_data"),
    )
    connection.autocommit = True
    return connection


def split_folder(folder: str) -> tuple[str, str]:
    """Делит каталог набора на код источника и код набора."""
    source_code, separator, dataset_code = folder.partition("/")
    if not separator:
        raise RegistryError(f"Ожидался путь <источник>/<набор>: {folder}")
    return source_code, dataset_code


def parse_fetched_at(file_path: Path) -> datetime:
    """Восстанавливает время снимка из имени файла."""
    try:
        moment = datetime.strptime(file_path.stem, "%Y-%m-%dT%H-%M-%SZ")
    except ValueError as error:
        raise RegistryError(
            f"Не удалось прочитать время из имени: {file_path.name}"
        ) from error
    return moment.replace(tzinfo=UTC)


def file_checksum(file_path: Path) -> str:
    """Считает sha256 файла, читая его по частям."""
    digest = sha256()
    with file_path.open("rb") as file:
        chunk = file.read(CHUNK_SIZE)
        while chunk:
            digest.update(chunk)
            chunk = file.read(CHUNK_SIZE)
    return digest.hexdigest()


def define_status(saved: int, errors: int) -> str:
    """Статус прогона по числу сохранённых наборов и ошибок."""
    if errors == 0:
        return "success"
    if saved == 0:
        return "failed"
    return "partial"


def save_copy_for_key(
    connection: psycopg.Connection, storage: str, object_key: str
) -> bool:
    """Отмечает копию объекта по уже записанной копии в RustFS.

    Снимок не создаётся заново: ключ ищется среди копий основного
    хранилища. Повторная запись ничего не меняет.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO orbital.snapshot_copies (snapshot_id, "
            "storage, object_key, file_size_bytes, status, copied_at) "
            "SELECT snapshot_id, %s, object_key, file_size_bytes, "
            "'ok', now() FROM orbital.snapshot_copies "
            "WHERE storage = %s AND object_key = %s "
            "ON CONFLICT (snapshot_id, storage) DO NOTHING",
            (storage, PRIMARY_STORAGE, object_key),
        )
        return cursor.rowcount > 0


def last_fetch_times(connection: psycopg.Connection) -> dict[str, datetime]:
    """Возвращает время последнего снимка по коду набора."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT d.code, max(sn.fetched_at) "
            "FROM orbital.snapshots sn "
            "JOIN orbital.datasets d USING (dataset_id) "
            "GROUP BY d.code"
        )
        return {code: last_fetch for code, last_fetch in cursor.fetchall()}


class RunRegistry:
    """Записывает ход прогона в PostgreSQL."""

    def __init__(self, connection: psycopg.Connection, run_id: int) -> None:
        self.connection = connection
        self.run_id = run_id

    @classmethod
    def start(cls) -> "RunRegistry":
        """Открывает запись прогона и возвращает реестр."""
        connection = connect()
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO orbital.runs (started_at) VALUES (%s) "
                "RETURNING run_id",
                (datetime.now(UTC),),
            )
            run_id = cursor.fetchone()[0]
        return cls(connection, run_id)

    def add_snapshot(
        self, folder: str, file_path: Path, fetched_at: datetime
    ) -> int:
        """Записывает снимок и возвращает его идентификатор."""
        source_code, dataset_code = split_folder(folder)
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT dataset_id FROM orbital.datasets "
                "WHERE source_id = (SELECT source_id "
                "FROM orbital.sources WHERE code = %s) AND code = %s",
                (source_code, dataset_code),
            )
            row = cursor.fetchone()
            if row is None:
                raise RegistryError(
                    f"Нет набора {folder} в справочнике orbital.datasets"
                )
            cursor.execute(
                "INSERT INTO orbital.snapshots (run_id, dataset_id, "
                "fetched_at, file_name, file_size_bytes, "
                "checksum_sha256, storage_path) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "RETURNING snapshot_id",
                (
                    self.run_id,
                    row[0],
                    fetched_at,
                    file_path.name,
                    file_path.stat().st_size,
                    file_checksum(file_path),
                    f"{folder}/{file_path.name}",
                ),
            )
            return cursor.fetchone()[0]

    def add_copy(
        self, snapshot_id: int, storage: str, object_key: str
    ) -> None:
        """Отмечает копию снимка в хранилище."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO orbital.snapshot_copies (snapshot_id, "
                "storage, object_key, file_size_bytes, status, "
                "copied_at) "
                "SELECT %s, %s, %s, file_size_bytes, 'ok', now() "
                "FROM orbital.snapshots WHERE snapshot_id = %s "
                "ON CONFLICT (snapshot_id, storage) DO NOTHING",
                (snapshot_id, storage, object_key, snapshot_id),
            )

    def finish(self, status: str, error_message: str = "") -> None:
        """Закрывает прогон итоговым статусом."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                "UPDATE orbital.runs SET finished_at = %s, status = %s, "
                "error_message = %s WHERE run_id = %s",
                (
                    datetime.now(UTC),
                    status,
                    error_message or None,
                    self.run_id,
                ),
            )

    def close(self) -> None:
        """Закрывает соединение с базой."""
        self.connection.close()
