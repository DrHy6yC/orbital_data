"""Правила удаления просроченных объектов бэкапа Bronze.

Модуль только решает, какие объекты вышли из своего окна хранения.
Удаление выполняет вызывающий код.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

CLOUD_BRONZE_PREFIX = "bronze/"
GZIP_SUFFIX = ".gz"
TIMESTAMP_FORMAT = "%Y-%m-%dT%H-%M-%SZ"


@dataclass
class RetentionPlan:
    """Просроченные объекты и объекты, к которым нет правил."""

    expired: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)


def snapshot_key(cloud_key: str) -> str:
    """Возвращает ключ снимка по ключу объекта облака.

    Облачная копия лежит с префиксом bronze/ и суффиксом .gz,
    у снимка в хранилище и в базе ни того, ни другого нет.
    """
    key = cloud_key.removeprefix(CLOUD_BRONZE_PREFIX)
    if key.endswith(GZIP_SUFFIX):
        key = key[: -len(GZIP_SUFFIX)]
    return key


def parse_key(key: str) -> tuple[str, datetime] | None:
    """Возвращает код набора и время снимка из ключа бэкапа."""
    if not key.startswith(CLOUD_BRONZE_PREFIX):
        return None
    parts = key.removeprefix(CLOUD_BRONZE_PREFIX).split("/")
    if len(parts) != 3:
        return None
    dataset = parts[1]
    file_name = parts[2]
    if file_name.endswith(GZIP_SUFFIX):
        file_name = file_name[: -len(GZIP_SUFFIX)]
    stem = file_name.rsplit(".", 1)[0]
    try:
        moment = datetime.strptime(stem, TIMESTAMP_FORMAT)
    except ValueError:
        return None
    return dataset, moment.replace(tzinfo=UTC)


def cloud_bronze_copies(
    cloud_objects: dict[str, int], expired: set[str]
) -> dict[str, tuple[str, int]]:
    """Возвращает облачные копии Bronze: ключ снимка и ключ облака с размером.

    Просроченные объекты не попадают: их удалит тот же запуск бэкапа,
    и отметка вела бы на отсутствующий объект. Дампы `postgres/`
    не попадают: у них нет снимка в базе.
    """
    copies = {}
    for cloud_key, size in sorted(cloud_objects.items()):
        if not cloud_key.startswith(CLOUD_BRONZE_PREFIX):
            continue
        if cloud_key in expired:
            continue
        copies[snapshot_key(cloud_key)] = (cloud_key, size)
    return copies


def find_newest_keys(cloud_objects: dict[str, int]) -> dict[str, str]:
    """Возвращает самый свежий ключ каждого набора."""
    latest: dict[str, tuple[datetime, str]] = {}
    for key in cloud_objects:
        parsed = parse_key(key)
        if parsed is None:
            continue
        dataset, moment = parsed
        if dataset not in latest or moment > latest[dataset][0]:
            latest[dataset] = (moment, key)
    newest: dict[str, str] = {}
    for dataset, (_, key) in latest.items():
        newest[dataset] = key
    return newest


def expired_keys(
    cloud_objects: dict[str, int],
    retention_days: dict[str, int],
    now: datetime,
) -> RetentionPlan:
    """Делит объекты бэкапа на просроченные и непонятные.

    Последний снимок каждого набора в просроченные не попадает:
    если загрузка набора остановилась, иначе в облаке не осталось бы
    ни одной копии.
    """
    plan = RetentionPlan()
    newest = find_newest_keys(cloud_objects)
    for key in sorted(cloud_objects):
        parsed = parse_key(key)
        if parsed is None:
            if key.startswith(CLOUD_BRONZE_PREFIX):
                plan.unknown.append(key)
            continue
        dataset, moment = parsed
        days = retention_days.get(dataset)
        if days is None:
            plan.unknown.append(key)
            continue
        if newest.get(dataset) == key:
            continue
        if (now - moment).days >= days:
            plan.expired.append(key)
    return plan
