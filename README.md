# Orbital Data Platform

Учебный проект по дата-инженерии: платформа для сбора, хранения, обработки
и анализа данных об искусственных спутниках и других орбитальных объектах.

## О проекте

Цель: собрать доступные данные из открытых источников, сохранить оригиналы
и историю изменений, обеспечить возможность повторной обработки. Проект
также служит площадкой для практики Data Engineering.

Что уже работает:

- этап 3: клиенты CelesTrak и Space-Track, загрузка пяти наборов, сохранение
  снимков источников в `data/`;
- этап 4 (частично): PostgreSQL и RustFS в Docker, локальный MinIO,
  проверка S3-хранилищ (`utils/check_s3.py`), подготовлен скрипт бэкапа
  в Yandex Object Storage (`utils/backup_to_cloud.py`).

Дальше: запись снимков в Bronze, дублирование в MinIO, метаданные
в PostgreSQL, Silver, ClickHouse. Подробности в [`PLAN.md`](PLAN.md).

## Технологический стек

Используется сейчас:

- **Python 3.12+** — основной язык разработки.
- **uv** — управление зависимостями и окружением.
- **httpx** — HTTP-клиент для загрузки данных.
- **boto3** — клиент S3 для проверок и бэкапа.
- **pytest** — тесты.
- **PostgreSQL** (Docker) — метаданные и операционная информация.
- **RustFS** (Docker) — основное S3-хранилище Bronze и Silver.
- **MinIO** (локально, без Docker) — дубль Bronze и Silver.
- **Yandex Object Storage** — внешний бэкап в пределах бесплатного уровня.

Запланировано:

- **Parquet / PyArrow** — слой Silver.
- **ClickHouse** — таблицы Silver и витрины Gold.
- **DuckDB** — локальные проверки Parquet.
- **dbt Core** (`dbt-clickhouse`) — преобразования и витрины.
- **psycopg** — доступ к PostgreSQL из загрузчика.
- **Apache Airflow** — оркестрация процессов.
- **FastAPI** — REST API.
- **SGP4** — орбитальные вычисления.

## Архитектура данных

Платформа использует архитектуру Lakehouse:

- **Bronze** — исходные данные без изменений, хранятся в S3.
- **Silver** — нормализованные и проверенные данные в Parquet, хранятся в S3.
- **Gold** — аналитические витрины, строятся в ClickHouse, в S3 не хранятся.

Роли хранилищ:

- **RustFS** — основное, в него пишут загрузчик и обработка.
- **MinIO** — локальный дубль Bronze и Silver.
- **Yandex Object Storage** — внешний бэкап Bronze и дампов PostgreSQL.

Роли хранилищ, схема ключей, лимиты и порядок восстановления:
[`docs/storage.md`](docs/storage.md).

## Источники данных

- **CelesTrak** — GP (TLE и OMM), SupGP, открытый доступ.
- **Space-Track** — GP, GP_History, SATCAT, DECAY, нужна регистрация.

Перечень источников: [`catalog.md`](docs/catalog.md).

Выбранные наборы и частота загрузки:
[`datasets.md`](docs/datasets.md).

## Структура проекта

        orbital_data/
    ├── src/orbital_data/
    │   ├── collectors/          клиенты CelesTrak и Space-Track
    │   └── source_snapshots/    запись снимков источников
    ├── sql/                     схемы PostgreSQL
    ├── tests/                   тесты
    ├── docs/
    │   ├── catalog.md           перечень источников данных
    │   ├── datasets.md          выбранные наборы и частота загрузки
    │   ├── storage.md           роли хранилищ и восстановление
    │   └── data_sources/
    │       ├── celestrak.md     описание CelesTrak
    │       └── space_track.md   описание Space-Track
    ├── utils/                   скрипты проверки, запуска и копирования
    ├── data/                    снимки и файлы исследований, в Git не входит
    ├── docker-compose.yml       PostgreSQL и RustFS
    ├── .env.example             образец настроек
    ├── PLAN.md                  план этапов
    ├── BACKLOG.md               активные задачи
    ├── COMMIT_RULES.md          правила коммитов
    ├── MINIO_INSTALL_LOCAL.md   установка и запуск MinIO без Docker
    ├── NOTES.md                 рабочие заметки
    └── README.md                описание проекта

---

## Запуск

Команды даны для macOS и Linux (bash, zsh). На Windows отличаются только
несколько команд, они вынесены в отдельный раздел ниже.

### Требования

- Python 3.12 или новее
- uv
- Git
- Docker (для PostgreSQL и RustFS)
- Go 1.24 или новее (только для локального MinIO)

### Получение проекта

```bash
git clone https://github.com/DrHy6yC/orbital_data.git
cd orbital_data
```

Обновить уже имеющуюся копию:

```bash
git pull
```

### Установка

```bash
uv sync
```

### Учётная запись Space-Track

Учётные данные Space-Track нужны для доступа к API. Регистрация
бесплатная, форма:
<https://www.space-track.org/auth/createAccount>.

При заполнении формы:

- `Interests` — `Educational (student)` или `Hobbyist`.
- `Organization` — название проекта или `Personal`.
- адрес, страна и телефон заполняются по требованиям формы,
  обязательные поля выделены;
- email подтверждается письмом с адреса `admin@space-track.org`,
  поэтому этот адрес стоит добавить в разрешённые.

Вход в созданную учётную запись:
<https://www.space-track.org/auth/login>.

### Настройка окружения

Скопировать образец:

```bash
cp .env.example .env
```

В `.env` собраны настройки в блоках: Space-Track (`SPACETRACK_*`),
PostgreSQL (`POSTGRES_*`), RustFS (`S3_RUSTFS_*`), MinIO (`S3_MINIO_*`)
и облако Yandex (`BACKUP_*`). Заполнить нужно как минимум учётные данные
Space-Track и пароли. Для CelesTrak учётные данные не нужны: доступ открытый.
Файл `.env` в Git не попадает, ключи Yandex хранить только в нём.

### PostgreSQL и RustFS (Docker)

Данные PostgreSQL лежат в `postgres-data/` и в Git не попадают, данные
RustFS в томе Docker `s3-data`.

```bash
docker compose up -d postgres s3
docker compose ps
```

### MinIO (локально, без Docker)

Установка Go и сборка MinIO описаны в
[`MINIO_INSTALL_LOCAL.md`](MINIO_INSTALL_LOCAL.md). Запуск (порты и ключи
берутся из `S3_MINIO_*` в `.env`):

```bash
chmod +x utils/run_minio.sh
./utils/run_minio.sh
```

Остановка: `Ctrl+C` в окне с сервером.

### Проверка хранилищ

Проверка всех S3-хранилищ, описанных в `.env` (создаёт бакеты `bronze`
и `silver`, пишет, читает и удаляет тестовые объекты):

```bash
uv run --env-file .env python utils/check_s3.py
```

### Команды запуска

Все команды выполняются из корня проекта.

Проверка подключения: по одному запросу к каждому источнику.

```bash
uv run --env-file .env python utils/check_connection.py
```

Загрузка пяти наборов и запись снимков в `data/`.

```bash
uv run --env-file .env python utils/check_download.py
```

Сверка форматов GP CelesTrak: разовое исследование, около 20 секунд
из-за паузы между запросами.

```bash
uv run python utils/compare_formats.py
```

Резервное копирование в Yandex Object Storage: сначала проверка доступа
и пробный запуск без загрузки.

```bash
uv run --env-file .env python utils/backup_to_cloud.py --check
uv run --env-file .env python utils/backup_to_cloud.py --dry-run
```

### Windows (PowerShell)

Отличаются только эти команды:

```powershell
Copy-Item .env.example .env
powershell -ExecutionPolicy Bypass -File utils\run_minio.ps1
```

Остальные команды `uv run ...` и `docker compose ...` одинаковы на всех
системах.

---

## Проверка и тестирование

### Тесты

```bash
uv run pytest
```

Тесты не обращаются к сети: HTTP-клиенты работают на `httpx.MockTransport`.
Проверяются разбор ответов, обработка ошибок и ограничений источников,
сохранение снимков и независимость источников друг от друга.

### Живая проверка

Скрипт `utils/check_download.py` печатает размер каждого сохранённого файла
и завершается с кодом 1, если источник вернул ошибку.

Источники ограничивают частоту: CelesTrak — не чаще раза в 2 часа на набор,
Space-Track `GP` — раз в час, `SATCAT` и `DECAY` — раз в день. При нарушении
приходит ошибка, поэтому повторять запрос сразу бесполезно.

### Куда сохраняются файлы

Снимки источников: `data/<источник>/<набор>/<время UTC>.ext`, например
`data/space_track/gp/2026-11-15T10-10-00Z.json`.

Файлы исследований: `data/research/celestrak/` — ответы, журналы запросов
и отчёт о сверке форматов.

Каталог `data/` в Git не входит.

---

## Планы и документация

- [`PLAN.md`](PLAN.md) — десять этапов проекта с подэтапами и статусами.
- [`BACKLOG.md`](BACKLOG.md) — задачи, которые выполняются сейчас.
- [`docs/storage.md`](docs/storage.md) — роли хранилищ, ключи, лимиты, восстановление.
- [`COMMIT_RULES.md`](COMMIT_RULES.md) — формат и правила коммитов.
- [`NOTES.md`](NOTES.md) — рабочие заметки.