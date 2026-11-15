# Активные задачи

Список незакрытых задач проекта. Выполненная задача удаляется из файла.
Этапы и подэтапы описаны в `PLAN.md`.

## Активные задачи

### 3.4. Сохранение исходных данных

**Файл и место:** `src/orbital_data/source_snapshots/save.py` (новый модуль),
`src/orbital_data/collectors/download.py`, `utils/check_download.py`,
`tests/test_save.py`, `tests/test_download.py`.

**Что нужно сделать:** сохранять каждый набор сразу после получения и не
накапливать ответы в памяти: один набор `space_track_gp` занимает 76 МБ,
все пять — около 152 МБ за прогон.

- каталоги взять из `datasets.md`: `data/celestrak/gp_stations/`,
  `data/celestrak/gp_active/`, `data/space_track/gp/`,
  `data/space_track/satcat/`, `data/space_track/decay/`;
- имя файла — время получения в UTC, например `2026-11-15T10-10-00Z.csv`;
- сначала запись в файл с расширением `.part`, затем переименование;
- существующий файл не перезаписывается;
- пустой ответ не сохраняется.

**Учесть:**
- исходный формат не меняется: CSV для CelesTrak, JSON для Space-Track;
- при отказе источника уже сохранённые наборы остаются, ошибка попадает
  в `errors`;
- `data/` не входит в Git;
- пакет называется `source_snapshots`, а не `storage`: шаблон `storage/`
  в `.gitignore` скрывает папку с таким именем на любой глубине.

**Ожидаемый результат:** после прогона в каждом каталоге лежит один файл
с исходным ответом.

**Как проверить:**
- `tests/test_save.py`: файл создаётся вместе с каталогами, существующий
  файл не перезаписывается, пустое тело отклоняется;
- `tests/test_download.py`: набор сохраняется сразу после получения, при
  ошибке источника ранее созданные файлы остаются;
- живой прогон выполняется командой
  `uv run --env-file .env python utils/check_download.py`, после чего
  проверяются каталоги `data/`.

**Осталось:** живой прогон после истечения окон частоты источников.

### 4.1. Настройка PostgreSQL

**Файл и место:** `docker-compose.yml` (новый файл), `.env.example`,
`sql/001_schema.sql` (новый файл), `README.md`.

**Что нужно сделать:** поднять PostgreSQL в Docker для метаданных
и сведений о загрузках.

- сервис `postgres` в `docker-compose.yml`: образ `postgres:17`, том
  `./postgres-data`, порт `5432`;
- учётные данные из `.env`: `POSTGRES_USER`, `POSTGRES_PASSWORD`,
  `POSTGRES_DB`;
- схема `orbital` и четыре таблицы: `sources`, `datasets`, `runs`,
  `snapshots`;
- проверка подключения без новых библиотек: `pg_isready` и `psql`
  внутри контейнера;
- раздел о подъёме базы в `README.md`.

**Ожидаемый результат:** контейнер запускается, `pg_isready` отвечает,
таблицы создаются, подключение к базе проверено.

**Как проверить:**
- `docker compose up -d postgres` и `docker compose ps` показывают
  состояние `healthy`;
- `docker compose exec -T postgres pg_isready -U orbital -d orbital_data`;
- `docker compose exec -T postgres psql -U orbital -d orbital_data -c "\dt orbital.*"`
  выводит четыре таблицы.

**Порядок работы:**
1. Агент готовит `docker-compose.yml`, дополняет `.env.example`, пишет
   черновик схемы и раздел в `README.md`.
2. Владелец проверяет схему, создаёт файлы и запускает контейнер.
3. Владелец применяет `sql/001_schema.sql` и проверяет таблицы.
4. Агент готовит текст коммита; коммит делает владелец.
