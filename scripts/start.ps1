param(
    [switch]$SeedDemo
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $ProjectRoot ".env"

if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
    Write-Error "Missing $EnvFile. Copy .env.example to .env and configure local MySQL before starting."
    exit 1
}

$VenvPython = Join-Path $ProjectRoot ".venv\\Scripts\\python.exe"
$PythonCommand = if (Test-Path -LiteralPath $VenvPython -PathType Leaf) {
    $VenvPython
} else {
    "python"
}

Set-Location -LiteralPath $ProjectRoot

& $PythonCommand manage.py migrate
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($SeedDemo) {
    & $PythonCommand manage.py seed_demo
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

& $PythonCommand manage.py runserver 0.0.0.0:8000
exit $LASTEXITCODE
