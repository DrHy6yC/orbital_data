# Локальный MinIO без Docker

Инструкция для Windows, Linux и macOS. Подходит только для локальной разработки:
community-редакция MinIO распространяется как исходный код и больше не
разрабатывается.

## 0. Что нужно

- Go версии 1.24 или выше (по README MinIO).
- Выход в интернет для `go install`.
- Свободные порты, указанные в `.env` (см. раздел 4).

## 1. Windows (PowerShell)

Установка Go:

```powershell
winget install --id GoLang.Go -e
```

Закрой PyCharm или PowerShell полностью и открой заново, затем:

```powershell
go version
go install github.com/minio/minio@latest
```

Если `go` не находится после перезапуска, вызови его по полному пути:

```powershell
& "C:\Program Files\Go\bin\go.exe" version
```

Готовый `minio.exe` появится в `%USERPROFILE%\go\bin`.

## 2. Linux (bash)

Пакеты `apt` и `dnf` часто содержат старый Go, поэтому надёжнее взять архив
с <https://go.dev/dl/> (файл вида `go<версия>.linux-amd64.tar.gz`; версию
подставь ту, что там указана):

```bash
sudo rm -rf /usr/local/go
sudo tar -C /usr/local -xzf go<версия>.linux-amd64.tar.gz
echo 'export PATH=$PATH:/usr/local/go/bin:$HOME/go/bin' >> ~/.bashrc
source ~/.bashrc
go version
go install github.com/minio/minio@latest
```

Для архитектуры ARM (например, Raspberry Pi) в имени архива вместо `amd64`
будет `arm64`. Бинарник появится в `~/go/bin`.

## 3. macOS (Terminal, Homebrew)

```bash
brew install go
go version
go install github.com/minio/minio@latest
```

Если Homebrew не установлен, сначала установи его с <https://brew.sh>, либо
возьми установщик `.pkg` с <https://go.dev/dl/>. Go собирает бинарник под
архитектуру твоего Mac (Intel или Apple Silicon) сам. Бинарник появится
в `~/go/bin`.

## 4. Настройки в `.env`

Каждое S3-хранилище проекта описывается пятью переменными. Имя хранилища
(`RUSTFS`, `MINIO`) входит в название переменной.

| Переменная | Что означает | Пример |
|---|---|---|
| `S3_<ИМЯ>_HOST` | Адрес, по которому клиент подключается | `localhost` |
| `S3_<ИМЯ>_PORT` | Порт S3 | `9002` |
| `S3_<ИМЯ>_CONSOLE_PORT` | Порт веб-консоли | `9003` |
| `S3_<ИМЯ>_ACCESS_KEY` | Логин | `orbital` |
| `S3_<ИМЯ>_SECRET_KEY` | Пароль | не короче 8 символов |

Пример для двух хранилищ:

```text
S3_RUSTFS_HOST=localhost
S3_RUSTFS_PORT=9000
S3_RUSTFS_CONSOLE_PORT=9001
S3_RUSTFS_ACCESS_KEY=orbital
S3_RUSTFS_SECRET_KEY=<пароль>

S3_MINIO_HOST=localhost
S3_MINIO_PORT=9002
S3_MINIO_CONSOLE_PORT=9003
S3_MINIO_ACCESS_KEY=orbital
S3_MINIO_SECRET_KEY=<пароль, не короче 8 символов>
```

Эти же переменные читают `docker-compose.yml` (RustFS), `utils/run_minio.*`
(MinIO) и `utils/check_s3.py` (проверка). Порты разных хранилищ должны
отличаться.

Особенности чтения `.env` скриптами запуска:

- читаются простые строки вида `ИМЯ=значение`, значения в кавычках допустимы;
- комментарий в конце строки войдёт в значение, поэтому комментарии пиши
  отдельной строкой;
- значения читаются только при запуске, после правки `.env` сервер нужно
  перезапустить;
- MinIO слушает только `127.0.0.1`, а `HOST` нужен клиентам (проверке).

## 5. Запуск MinIO

Из корня проекта. Данные хранятся в `storage/minio` (каталог уже в
`.gitignore`, запись `storage/`).

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File utils\run_minio.ps1
```

Ключ `-ExecutionPolicy Bypass` действует только на этот запуск. Сообщения
в скриптах на английском намеренно: Windows PowerShell 5 читает `.ps1` без BOM
в старой кодировке и портит кириллицу.

Linux и macOS:

```bash
chmod +x utils/run_minio.sh
./utils/run_minio.sh
```

Скрипт печатает адреса S3 и консоли. Остановка: `Ctrl+C`.

## 6. Проверка

Быстрая проверка живости (второе окно терминала, порт из `.env`):

```bash
curl -i http://127.0.0.1:<S3_MINIO_PORT>/minio/health/live
```

В Windows используй `curl.exe`. Ожидаемый результат: `HTTP/1.1 200 OK`.
Консоль: `http://127.0.0.1:<S3_MINIO_CONSOLE_PORT>`, вход по логину и паролю
из `.env`.

Полная проверка всех хранилищ из `.env` (бакеты, запись, чтение, многочастная
загрузка):

```bash
uv run --env-file .env python utils/check_s3.py
```

## 7. Частые проблемы

| Симптом | Причина и решение |
|---|---|
| `go` не найден после установки | Терминал не видит обновлённый `PATH`: перезапусти терминал или IDE целиком либо вызови Go по полному пути |
| `minio` не найден | Каталог `~/go/bin` (Windows: `%USERPROFILE%\go\bin`) не в `PATH`; скрипты запуска ищут его там сами |
| `go install` пишет об ошибке версии Go | Установлен Go ниже 1.24: обнови |
| Скрипт пишет `... is not set in .env` | В `.env` нет указанной переменной из раздела 4 |
| MinIO не стартует, ошибка про длину ключа | Пароль короче 8 символов или логин короче 3 |
| Порт занят | Другой процесс использует порт (в том числе контейнер `s3`): смени порт в `.env` или останови процесс |
| Проверка: `InvalidAccessKeyId` или `SignatureDoesNotMatch` | Хранилище запущено со старыми ключами: перезапусти его (для контейнера `docker compose up -d --force-recreate s3`) |