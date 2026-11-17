"""Измеряет сжатие gzip на локальных снимках из data/.

Разовая проверка для подэтапа 4.6: сколько займёт Bronze в облаке
после сжатия. Скрипт только читает, ничего не пишет и не удаляет.
Запуск из корня проекта:
    uv run python utils/measure_gzip.py
"""

import gzip
from collections import defaultdict
from pathlib import Path

DATA_DIRECTORY = Path(__file__).resolve().parent.parent / "data"
COMPRESS_LEVEL = 9
MIB = 1024 * 1024


def dataset_name(file_path: Path) -> str | None:
    """Возвращает <источник>/<набор> по пути внутри data/."""
    parts = file_path.relative_to(DATA_DIRECTORY).parts
    if len(parts) < 3:
        return None
    return f"{parts[0]}/{parts[1]}"


def main() -> None:
    if not DATA_DIRECTORY.is_dir():
        print(f"Каталог не найден: {DATA_DIRECTORY}")
        return
    counts: dict[str, int] = defaultdict(int)
    raw_sizes: dict[str, int] = defaultdict(int)
    packed_sizes: dict[str, int] = defaultdict(int)
    for file_path in sorted(DATA_DIRECTORY.rglob("*")):
        if not file_path.is_file():
            continue
        name = dataset_name(file_path)
        if name is None:
            continue
        data = file_path.read_bytes()
        packed = gzip.compress(data, compresslevel=COMPRESS_LEVEL)
        counts[name] += 1
        raw_sizes[name] += len(data)
        packed_sizes[name] += len(packed)
    if not raw_sizes:
        print("В каталоге data/ нет снимков")
        return
    show_table(counts, raw_sizes, packed_sizes)


def show_table(
    counts: dict[str, int],
    raw_sizes: dict[str, int],
    packed_sizes: dict[str, int],
) -> None:
    """Печатает размеры по наборам и коэффициент сжатия."""
    for name in sorted(raw_sizes):
        raw_mib = raw_sizes[name] / MIB
        packed_mib = packed_sizes[name] / MIB
        ratio = raw_sizes[name] / packed_sizes[name]
        average = packed_mib / counts[name]
        print(
            f"{name}: снимков {counts[name]}, "
            f"{raw_mib:.2f} МиБ -> {packed_mib:.2f} МиБ, "
            f"сжатие {ratio:.2f}, "
            f"в среднем {average:.2f} МиБ на снимок"
        )
    total_raw = sum(raw_sizes.values())
    total_packed = sum(packed_sizes.values())
    print(
        f"всего: {total_raw / MIB:.2f} МиБ -> "
        f"{total_packed / MIB:.2f} МиБ, "
        f"сжатие {total_raw / total_packed:.2f}"
    )


if __name__ == "__main__":
    main()
