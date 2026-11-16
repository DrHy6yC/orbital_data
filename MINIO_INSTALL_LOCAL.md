# Локальный MinIO без Docker

Инструкция для Windows, Linux и macOS. Подходит только для локальной разработки:
community-редакция MinIO распространяется как исходный код и больше не
разрабатывается.

## 0. Что нужно

- Go версии 1.24 или выше (по README MinIO).
- Выход в интернет для `go install`.
- Свободные порты 9000 (S3) и 9001 (консоль).

## 1. Windows (PowerShell)

Установка Go и проверка:

```powershell
winget install --id GoLang.Go -e
```

Закрой PyCharm или PowerShell полностью и открой заново, затем:

```powershell
go version
```

Сборка и запуск (из корня проекта):

```powershell
go install github.com/minio/minio@latest
New-Item -ItemType Directory storage\minio -Force
$env:MINIO_ROOT_USER = "<логин>"
$env:MINIO_ROOT_PASSWORD = "<пароль, не короче 8 символов>"
& "$env:USERPROFILE\go\bin\minio.exe" server storage\minio --address 127.0.0.1:9000 --console-address 127.0.0.1:9001
```

Если `go` не находится после перезапуска, вызови его по полному пути:

```powershell
& "C:\Program Files\Go\bin\go.exe" version
```

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
```

Сборка и запуск (из корня проекта):

```bash
go install github.com/minio/minio@latest
mkdir -p storage/minio
export MINIO_ROOT_USER="<логин>"
export MINIO_ROOT_PASSWORD="<пароль, не короче 8 символов>"
minio server storage/minio --address 127.0.0.1:9000 --console-address 127.0.0.1:9001
```

Для архитектуры ARM (например, Raspberry Pi) в имени архива вместо `amd64`
будет `arm64`.

## 3. macOS (Terminal, Homebrew)

```bash
brew install go
go version
```

Если Homebrew не установлен, сначала установи его с <https://brew.sh>, либо
возьми установщик `.pkg` с <https://go.dev/dl/>.

Сборка и запуск (из корня проекта):

```bash
go install github.com/minio/minio@latest
mkdir -p storage/minio
export PATH="$PATH:$HOME/go/bin"
export MINIO_ROOT_USER="<логин>"
export MINIO_ROOT_PASSWORD="<пароль, не короче 8 символов>"
minio server storage/minio --address 127.0.0.1:9000 --console-address 127.0.0.1:9001
```

Go собирает бинарник под архитектуру твоего Mac (Intel или Apple Silicon) сам.

## 4. Проверка (одинакова для всех систем)

Открой второе окно терминала:

```bash
curl -i http://127.0.0.1:9000/minio/health/live
```

В Windows используй `curl.exe` вместо `curl`.

Ожидаемый результат: `HTTP/1.1 200 OK`, консоль открывается на
<http://127.0.0.1:9001>, вход по логину и паролю, заданным выше.

Остановка: `Ctrl+C` в окне с сервером. Данные остаются в каталоге
`storage/minio`, он уже есть в `.gitignore` (запись `storage/`).

## 5. Запуск с логином и паролем из `.env`

Скрипты читают `S3_ACCESS_KEY` и `S3_SECRET_KEY` из `.env` (те же переменные,
что использует сервис `s3` в `docker-compose.yml`) и передают их MinIO как
`MINIO_ROOT_USER` и `MINIO_ROOT_PASSWORD`. Если в `.env` другие имена,
замени их в блоке чтения.

Особенности:

- читаются простые строки вида `ИМЯ=значение`, значения в кавычках допустимы;
- комментарий в конце строки войдёт в значение, поэтому комментарии пиши
  отдельной строкой;
- ключи читаются только при запуске, после правки `.env` сервер нужно
  перезапустить;
- порты те же, что у сервиса `s3` в compose: перед запуском останови
  контейнер (`docker compose stop s3`).

### 5.1. Windows: `utils/run_minio.ps1`

```powershell
# Local MinIO launcher: reads S3_ACCESS_KEY and S3_SECRET_KEY from .env
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"
if (-not (Test-Path $envFile)) { throw ".env not found: $envFile" }

$vars = @{}
foreach ($line in Get-Content $envFile -Encoding UTF8) {
    $line = $line.Trim()
    if ($line -eq "" -or $line.StartsWith("#") -or $line -notmatch "=") { continue }
    $name, $value = $line -split "=", 2
    $vars[$name.Trim()] = $value.Trim().Trim('"').Trim("'")
}

foreach ($required in "S3_ACCESS_KEY", "S3_SECRET_KEY") {
    if (-not $vars[$required]) { throw "$required is not set in .env" }
}

$env:MINIO_ROOT_USER = $vars["S3_ACCESS_KEY"]
$env:MINIO_ROOT_PASSWORD = $vars["S3_SECRET_KEY"]

$dataDir = Join-Path $root "storage\minio"
New-Item -ItemType Directory $dataDir -Force | Out-Null

$minio = Join-Path $env:USERPROFILE "go\bin\minio.exe"
if (-not (Test-Path $minio)) { throw "minio.exe not found: $minio" }

& $minio server $dataDir --address 127.0.0.1:9000 --console-address 127.0.0.1:9001
```

Запуск из корня проекта (ключ `-ExecutionPolicy Bypass` действует только на этот
запуск):

```powershell
powershell -ExecutionPolicy Bypass -File utils\run_minio.ps1
```

Сообщения в скрипте на английском намеренно: Windows PowerShell 5 читает `.ps1`
без BOM в старой кодировке и портит кириллицу.

### 5.2. Linux и macOS: `utils/run_minio.sh`

```bash
#!/usr/bin/env bash
# Local MinIO launcher: reads S3_ACCESS_KEY and S3_SECRET_KEY from .env
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
[ -f "$ENV_FILE" ] || { echo ".env not found: $ENV_FILE" >&2; exit 1; }

get_var() {
  grep -E "^$1=" "$ENV_FILE" | tail -n1 | cut -d= -f2- | tr -d '\r' \
    | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

S3_ACCESS_KEY="$(get_var S3_ACCESS_KEY || true)"
S3_SECRET_KEY="$(get_var S3_SECRET_KEY || true)"
[ -n "$S3_ACCESS_KEY" ] || { echo "S3_ACCESS_KEY is not set in .env" >&2; exit 1; }
[ -n "$S3_SECRET_KEY" ] || { echo "S3_SECRET_KEY is not set in .env" >&2; exit 1; }

export MINIO_ROOT_USER="$S3_ACCESS_KEY"
export MINIO_ROOT_PASSWORD="$S3_SECRET_KEY"

DATA_DIR="$ROOT/storage/minio"
mkdir -p "$DATA_DIR"

MINIO_BIN="$(command -v minio || echo "$HOME/go/bin/minio")"
[ -x "$MINIO_BIN" ] || { echo "minio not found: $MINIO_BIN" >&2; exit 1; }

exec "$MINIO_BIN" server "$DATA_DIR" --address 127.0.0.1:9000 --console-address 127.0.0.1:9001
```

Подготовка и запуск из корня проекта:

```bash
chmod +x utils/run_minio.sh
./utils/run_minio.sh
```
