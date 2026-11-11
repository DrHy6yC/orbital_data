"""Сверка форматов GP CelesTrak (JSON и CSV) на реальных ответах.

Скрипт делает по одному запросу на каждую пару "группа + формат", сохраняет
исходные ответы без изменений и строит отчёт о расхождениях с описанием
в celestrak_research.md (раздел 2.5).

Правила, которые соблюдает скрипт (политика использования CelesTrak):
- каждый набор запрашивается один раз, повторов нет;
- между запросами пауза;
- при любом ответе, отличном от HTTP 200, или при нетипичном теле ответа
  скрипт немедленно останавливается и ничего не повторяет.

Запуск из корня проекта:
    uv run python docs/research/celestrak/scripts/compare_formats.py

Ответы, журнал запросов и отчёт сохраняются в data/celestrak/responses.
Каталог data не входит в Git, поэтому ответы остаются локальными.
"""

import csv
import io
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def find_project_root(start: Path) -> Path:
    """Возвращает ближайший каталог вверх по дереву с файлом pyproject.toml."""
    for folder in (start, *start.parents):
        if (folder / "pyproject.toml").is_file():
            return folder
    raise SystemExit("Не найден pyproject.toml: запускать из корня проекта")


PROJECT_ROOT = find_project_root(Path(__file__).resolve().parent)
OUT_DIR = PROJECT_ROOT / "data" / "celestrak" / "responses"

BASE_URL = "https://celestrak.org/NORAD/elements/gp.php"
GROUPS = ["STATIONS", "ANALYST"]
FORMATS = ["JSON", "CSV"]
CONSTANT_FIELDS = ["CENTER_NAME", "REF_FRAME", "TIME_SYSTEM", "MEAN_ELEMENT_THEORY"]
LONG_NUMBER_LIMIT = 100000
PAUSE_SECONDS = 5
TIMEOUT_SECONDS = 60
USER_AGENT = "orbital-data-research/0.1 (learning project)"
ERROR_PREFIXES = ("invalid query", "no gp data found")
EXTENSIONS = {"JSON": "json", "CSV": "csv"}


def fetch(group: str, fmt: str) -> dict:
    """Выполняет один запрос и возвращает сведения об ответе вместе с телом."""
    url = f"{BASE_URL}?{urlencode({'GROUP': group, 'FORMAT': fmt})}"
    request = Request(url, headers={"User-Agent": USER_AGENT})
    started = time.monotonic()
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status, final_url = response.status, response.geturl()
            headers, body = dict(response.headers.items()), response.read()
    except HTTPError as error:
        status, final_url = error.code, error.url
        headers, body = dict(error.headers.items()), error.read()
    except URLError as error:
        raise SystemExit(f"Сетевая ошибка для {url}: {error.reason}")
    return {
        "group": group,
        "format": fmt,
        "url": url,
        "final_url": final_url,
        "status": status,
        "content_type": headers.get("Content-Type"),
        "content_length_header": headers.get("Content-Length"),
        "last_modified": headers.get("Last-Modified"),
        "etag": headers.get("ETag"),
        "size_bytes": len(body),
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "received_at_utc": datetime.now(timezone.utc).isoformat(),
        "body": body,
    }


def problem_with(record: dict) -> str | None:
    """Возвращает описание проблемы с ответом или None, если ответ допустим."""
    if record["status"] != 200:
        return f"HTTP {record['status']}"
    if record["final_url"] != record["url"]:
        return f"перенаправление на {record['final_url']}"
    head = record["body"][:200].decode("utf-8", errors="replace").strip().lower()
    if not head:
        return "пустое тело ответа"
    if head.startswith(ERROR_PREFIXES):
        return f"тело ответа похоже на сообщение об ошибке: {head[:80]}"
    return None


def parse_json(body: bytes) -> list[dict]:
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
        raise ValueError("JSON не является списком объектов")
    return data


def parse_csv(body: bytes) -> tuple[list[str], list[dict]]:
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
    rows = list(reader)
    return list(reader.fieldnames or []), rows


def same_value(json_value, csv_value: str) -> bool:
    """Сравнивает значение из JSON со значением из CSV (в CSV всё строки)."""
    if json_value is None:
        return csv_value == ""
    if isinstance(json_value, bool):
        return str(json_value).lower() == csv_value.lower()
    if isinstance(json_value, (int, float)):
        try:
            return float(json_value) == float(csv_value)
        except ValueError:
            return False
    return str(json_value) == csv_value


def index_by_id(rows: list[dict]) -> tuple[dict, int]:
    """Индекс записей по NORAD_CAT_ID и число повторяющихся идентификаторов."""
    index, duplicates = {}, 0
    for row in rows:
        key = int(row["NORAD_CAT_ID"])
        if key in index:
            duplicates += 1
        index[key] = row
    return index, duplicates


def compare(group, json_record, csv_record) -> list[str]:
    json_rows = parse_json(json_record["body"])
    csv_fields, csv_rows = parse_csv(csv_record["body"])
    json_keys = set().union(*(row.keys() for row in json_rows)) if json_rows else set()
    in_every_json = (
        set.intersection(*(set(row.keys()) for row in json_rows)) if json_rows else set()
    )
    csv_keys = set(csv_fields)

    lines = [f"## Группа {group}", ""]
    lines += [
        "| Показатель | JSON | CSV |",
        "|---|---|---|",
        f"| HTTP-статус | {json_record['status']} | {csv_record['status']} |",
        f"| Content-Type | {json_record['content_type']} | {csv_record['content_type']} |",
        f"| Размер ответа, байт | {json_record['size_bytes']} | {csv_record['size_bytes']} |",
        f"| Число записей | {len(json_rows)} | {len(csv_rows)} |",
        f"| Число полей | {len(json_keys)} | {len(csv_keys)} |",
        "",
        f"Отношение размера JSON к CSV: "
        f"{json_record['size_bytes'] / max(csv_record['size_bytes'], 1):.2f}",
        "",
    ]

    lines += ["### Постоянные поля OMM", "", "| Поле | Есть в JSON | Есть в CSV |", "|---|---|---|"]
    for field in CONSTANT_FIELDS:
        lines.append(f"| {field} | {field in json_keys} | {field in csv_keys} |")
    lines.append("")

    lines += ["### Состав полей", ""]
    lines.append(f"- Только в JSON: {sorted(json_keys - csv_keys) or 'нет'}")
    lines.append(f"- Только в CSV: {sorted(csv_keys - json_keys) or 'нет'}")
    lines.append(
        f"- В JSON есть не в каждой записи: {sorted(json_keys - in_every_json) or 'нет'}"
    )
    lines.append(f"- Порядок полей в CSV: {csv_fields}")
    lines.append("")

    lines += ["### Типы значений в JSON", "", "| Поле | Типы (число записей) |", "|---|---|"]
    for field in sorted(json_keys):
        types = Counter(
            type(row[field]).__name__ if field in row else "отсутствует"
            for row in json_rows
        )
        lines.append(f"| {field} | {dict(types)} |")
    lines.append("")

    empty_csv = {f: sum(1 for r in csv_rows if r.get(f, "") == "") for f in csv_fields}
    empty_csv = {f: n for f, n in empty_csv.items() if n}
    null_json = {
        f: sum(1 for r in json_rows if r.get(f) is None) for f in sorted(json_keys)
    }
    null_json = {f: n for f, n in null_json.items() if n}
    lines += [
        "### Пустые значения",
        "",
        f"- JSON, значение null: {null_json or 'нет'}",
        f"- CSV, пустая строка: {empty_csv or 'нет'}",
        "",
    ]

    json_index, json_dups = index_by_id(json_rows)
    csv_index, csv_dups = index_by_id(csv_rows)
    common = sorted(set(json_index) & set(csv_index))
    lines += [
        "### Идентификаторы",
        "",
        f"- Тип NORAD_CAT_ID в JSON: "
        f"{dict(Counter(type(r['NORAD_CAT_ID']).__name__ for r in json_rows))}",
        f"- Повторяющиеся идентификаторы: JSON {json_dups}, CSV {csv_dups}",
        f"- Идентификаторы только в JSON: {sorted(set(json_index) - set(csv_index))[:10] or 'нет'}",
        f"- Идентификаторы только в CSV: {sorted(set(csv_index) - set(json_index))[:10] or 'нет'}",
        "",
    ]

    long_json = sorted(i for i in json_index if i >= LONG_NUMBER_LIMIT)
    long_csv = sorted(i for i in csv_index if i >= LONG_NUMBER_LIMIT)
    lines += [
        f"### Объекты с номером {LONG_NUMBER_LIMIT} и выше",
        "",
        f"- JSON: {len(long_json)} объектов, примеры {long_json[:5]}",
        f"- CSV: {len(long_csv)} объектов, примеры {long_csv[:5]}",
        f"- Наибольший номер: JSON {max(json_index, default=None)}, CSV {max(csv_index, default=None)}",
        "",
    ]

    mismatches, compared = [], 0
    for key in common:
        for field in csv_keys & set(json_index[key].keys()):
            compared += 1
            if not same_value(json_index[key][field], csv_index[key][field]):
                mismatches.append((key, field, json_index[key][field], csv_index[key][field]))
    lines += [
        "### Сравнение значений",
        "",
        f"- Сопоставлено значений: {compared}",
        f"- Расхождений: {len(mismatches)}",
    ]
    for key, field, j_val, c_val in mismatches[:10]:
        lines.append(f"  - {key}, {field}: JSON {j_val!r}, CSV {c_val!r}")
    lines.append("")

    if json_rows:
        lines += [
            "### Пример записи JSON",
            "",
            "```json",
            json.dumps(json_rows[0], ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    return lines


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    records: dict[tuple[str, str], dict] = {}
    log: list[dict] = []

    first = True
    for group in GROUPS:
        for fmt in FORMATS:
            if not first:
                time.sleep(PAUSE_SECONDS)
            first = False
            record = fetch(group, fmt)
            log.append({k: v for k, v in record.items() if k != "body"})
            name = f"gp_{group.lower()}_{fmt.lower()}_{stamp}.{EXTENSIONS[fmt]}"
            (OUT_DIR / name).write_bytes(record["body"])
            problem = problem_with(record)
            print(f"{group} {fmt}: HTTP {record['status']}, {record['size_bytes']} байт")
            if problem:
                (OUT_DIR / f"requests_log_{stamp}.json").write_text(
                    json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                sys.exit(f"Остановка: {problem}. Запросы прекращены, повторов нет.")
            records[(group, fmt)] = record

    report = ["# Сверка форматов GP: JSON и CSV", "", f"Время запуска (UTC): {stamp}", ""]
    for group in GROUPS:
        report += compare(group, records[(group, "JSON")], records[(group, "CSV")])

    (OUT_DIR / f"requests_log_{stamp}.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report_path = OUT_DIR / f"format_comparison_{stamp}.md"
    report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Отчёт: {report_path}")


if __name__ == "__main__":
    main()