"""Применяет SQL-файлы к базе метаданных.

Файлы применяются по порядку в одной транзакции: если один из них
завершится ошибкой, база останется в состоянии до запуска.
Можно передать отдельные файлы или каталог: из каталога берутся все
файлы с расширением .sql в порядке имён. Файлы читаются как UTF-8,
поэтому русские названия не зависят от кодировки консоли.

Запуск из корня проекта:
    uv run --env-file .env python utils/apply_sql.py sql
    uv run --env-file .env python utils/apply_sql.py sql/002_seed.sql
"""

import argparse
import os
import sys
from pathlib import Path

import psycopg


def load_settings() -> dict[str, str]:
    """Собирает параметры подключения из переменных окружения."""
    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        sys.exit("Не задан POSTGRES_PASSWORD, проверьте .env")
    return {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "user": os.environ.get("POSTGRES_USER", "orbital"),
        "password": password,
        "dbname": os.environ.get("POSTGRES_DB", "orbital_data"),
    }


def collect_files(names: list[str]) -> list[Path]:
    """Разворачивает аргументы в список SQL-файлов в нужном порядке."""
    files: list[Path] = []
    for name in names:
        path = Path(name)
        if path.is_dir():
            files.extend(sorted(path.glob("*.sql")))
        elif path.is_file():
            files.append(path)
        else:
            sys.exit(f"Файл или каталог не найден: {name}")
    return files


def apply_files(connection: psycopg.Connection, files: list[Path]) -> int:
    """Выполняет файлы по очереди. Возвращает число применённых."""
    applied = 0
    with connection.cursor() as cursor:
        for path in files:
            sql = path.read_text(encoding="utf-8-sig")
            if not sql.strip():
                print(f"{path.name}: пустой файл, пропущен")
                continue
            cursor.execute(sql)
            applied += 1
            print(f"{path.name}: применён")
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Применяет SQL-файлы к базе метаданных",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="SQL-файлы или каталог с ними; порядок сохраняется",
    )
    args = parser.parse_args()

    files = collect_files(args.files)
    if not files:
        sys.exit("В каталоге нет SQL-файлов")

    settings = load_settings()
    print(
        f"Подключение: {settings['user']}@{settings['host']}:"
        f"{settings['port']}/{settings['dbname']}"
    )
    try:
        with psycopg.connect(**settings) as connection:
            applied = apply_files(connection, files)
    except psycopg.Error as error:
        sys.exit(f"Ошибка при применении: {error}")

    print(f"Готово, файлов применено: {applied}")


if __name__ == "__main__":
    main()
