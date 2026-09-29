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

# Detect active physical Ethernet/Wi-Fi adapters on every startup.
$LanAddresses = @()
try {
    $AdapterIndexes = @(Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | Select-Object -ExpandProperty ifIndex)
    $LanAddresses = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        $_.InterfaceIndex -in $AdapterIndexes -and
        $_.AddressState -eq 'Preferred' -and
        $_.IPAddress -notmatch '^(127\.|169\.254\.|0\.)'
    } | Select-Object -ExpandProperty IPAddress -Unique)
} catch {
    Write-Warning "Could not detect LAN addresses: $($_.Exception.Message)"
}

$PreviousLanHosts = $env:DJANGO_LAN_HOSTS
try {
    $env:DJANGO_LAN_HOSTS = (@('127.0.0.1', 'localhost') + $LanAddresses) -join ','
    Write-Host 'Local: http://127.0.0.1:8000/login/'
    foreach ($LanAddress in $LanAddresses) {
        Write-Host "LAN login: http://${LanAddress}:8000/login/"
        Write-Host "LAN admin: http://${LanAddress}:8000/manage/"
        Write-Host "LAN mobile: http://${LanAddress}:8000/m/"
    }
    if ($LanAddresses.Count -eq 0) {
        Write-Warning 'No active LAN IPv4 address found. Connect Ethernet/Wi-Fi and restart this script.'
    }
    & $PythonCommand manage.py runserver 0.0.0.0:8000
    $ServerExitCode = $LASTEXITCODE
} finally {
    $env:DJANGO_LAN_HOSTS = $PreviousLanHosts
}
exit $ServerExitCode
