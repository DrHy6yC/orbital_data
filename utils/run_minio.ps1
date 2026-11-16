# Local MinIO launcher: reads S3_MINIO_* settings from .env
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

foreach ($required in "S3_MINIO_PORT", "S3_MINIO_CONSOLE_PORT", "S3_MINIO_ACCESS_KEY", "S3_MINIO_SECRET_KEY") {
    if (-not $vars[$required]) { throw "$required is not set in .env" }
}

$env:MINIO_ROOT_USER = $vars["S3_MINIO_ACCESS_KEY"]
$env:MINIO_ROOT_PASSWORD = $vars["S3_MINIO_SECRET_KEY"]
$port = $vars["S3_MINIO_PORT"]
$consolePort = $vars["S3_MINIO_CONSOLE_PORT"]

$dataDir = Join-Path $root "storage\minio"
New-Item -ItemType Directory $dataDir -Force | Out-Null

$minio = Join-Path $env:USERPROFILE "go\bin\minio.exe"
if (-not (Test-Path $minio)) { throw "minio.exe not found: $minio" }

Write-Host "MinIO: S3 http://127.0.0.1:$port, console http://127.0.0.1:$consolePort"
& $minio server $dataDir --address "127.0.0.1:$port" --console-address "127.0.0.1:$consolePort"
