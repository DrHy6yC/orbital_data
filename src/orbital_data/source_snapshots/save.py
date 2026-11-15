"""Сохранение исходных ответов без изменений."""

from pathlib import Path


def save_original(body: bytes, file_path: Path) -> Path:
    """Записывает тело ответа целиком или не записывает вовсе.

    Временный файл нужен, чтобы недописанный ответ не попал в набор
    данных под основным именем.
    """
    if not body:
        raise ValueError(f"Пустой ответ, файл не создан: {file_path}")
    if file_path.exists():
        raise FileExistsError(f"Файл уже существует: {file_path}")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = file_path.with_name(file_path.name + ".part")
    temporary_path.write_bytes(body)
    temporary_path.replace(file_path)
    return file_path
