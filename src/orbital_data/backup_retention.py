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


def expired_keys(
    cloud_objects: dict[str, int],
    retention_days: dict[str, int],
    now: datetime,
) -> RetentionPlan:
    """Делит объекты бэкапа на просроченные и непонятные."""
    plan = RetentionPlan()
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
        if (now - moment).days >= days:
            plan.expired.append(key)
    return plan
