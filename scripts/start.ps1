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

$LocalMkcert = Join-Path $ProjectRoot '.tools\mkcert.exe'
$MkcertCommand = Get-Command mkcert -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $LocalMkcert -PathType Leaf) {
    $MkcertPath = $LocalMkcert
} elseif ($MkcertCommand) {
    $MkcertPath = $MkcertCommand.Source
} else {
    $ToolsDirectory = Split-Path -Parent $LocalMkcert
    $DownloadPath = "$LocalMkcert.download"
    New-Item -ItemType Directory -Path $ToolsDirectory -Force | Out-Null
    try {
        Write-Host 'mkcert was not found; downloading the official Windows binary...'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri 'https://dl.filippo.io/mkcert/latest?for=windows/amd64' -OutFile $DownloadPath -UseBasicParsing
        Move-Item -LiteralPath $DownloadPath -Destination $LocalMkcert -Force
        $MkcertPath = $LocalMkcert
    } catch {
        Remove-Item -LiteralPath $DownloadPath -Force -ErrorAction SilentlyContinue
        Write-Error 'Could not download mkcert. Install it with Chocolatey (choco install mkcert), Scoop (scoop install mkcert), or download the Windows binary from https://github.com/FiloSottile/mkcert/releases and save it as .tools\mkcert.exe.'
        exit 1
    }
}

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
$PhysicalAddresses = @()
try {
    $AdapterIndexes = @(Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | Select-Object -ExpandProperty ifIndex)
    $PhysicalAddresses = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        $_.InterfaceIndex -in $AdapterIndexes -and
        $_.AddressState -eq 'Preferred' -and
        $_.IPAddress -notmatch '^(127\.|169\.254\.|0\.)'
    })
    $LanAddresses = @($PhysicalAddresses | Select-Object -ExpandProperty IPAddress -Unique)
} catch {
    Write-Warning "Could not detect LAN addresses: $($_.Exception.Message)"
}

$TiandituDirectEnabled = Select-String -LiteralPath $EnvFile -Pattern '^\s*TIANDITU_DIRECT_EGRESS\s*=\s*true\s*$' -Quiet
$TiandituDirectRoute = $null
if ($TiandituDirectEnabled) {
    foreach ($Address in $PhysicalAddresses) {
        try {
            $DnsServers = @((Get-DnsClientServerAddress -InterfaceIndex $Address.InterfaceIndex -AddressFamily IPv4 -ErrorAction Stop).ServerAddresses | Where-Object { $_ })
            if ($DnsServers.Count -gt 0) {
                $TiandituDirectRoute = [PSCustomObject]@{
                    SourceIP = $Address.IPAddress
                    InterfaceIndex = $Address.InterfaceIndex
                    DnsServers = $DnsServers -join ','
                }
                break
            }
        } catch {
            Write-Warning "Could not read DNS servers for physical interface $($Address.InterfaceIndex): $($_.Exception.Message)"
        }
    }
    if (-not $TiandituDirectRoute) {
        Write-Error 'Tianditu physical direct connection is enabled, but no active physical IPv4 adapter with DNS servers was found.'
        exit 1
    }
}

$CertificateDirectory = Join-Path $ProjectRoot '.certs'
$CertificateFile = Join-Path $CertificateDirectory 'lan.pem'
$PrivateKeyFile = Join-Path $CertificateDirectory 'lan-key.pem'
$MobileRootCertificate = Join-Path $CertificateDirectory 'mobile-rootCA.pem'
New-Item -ItemType Directory -Path $CertificateDirectory -Force | Out-Null

& $MkcertPath -install
if ($LASTEXITCODE -ne 0) {
    Write-Error 'mkcert could not install its local CA. Retry from an elevated PowerShell window, then run this script again.'
    exit $LASTEXITCODE
}

$CertificateNames = @('localhost', '127.0.0.1') + $LanAddresses
& $MkcertPath -cert-file $CertificateFile -key-file $PrivateKeyFile @CertificateNames
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$CaDirectory = (& $MkcertPath -CAROOT | Select-Object -Last 1).Trim()
$CaCertificate = Join-Path $CaDirectory 'rootCA.pem'
if (-not (Test-Path -LiteralPath $CaCertificate -PathType Leaf)) {
    Write-Error "mkcert root CA was not found at $CaCertificate. Run 'mkcert -install' and retry."
    exit 1
}
Copy-Item -LiteralPath $CaCertificate -Destination $MobileRootCertificate -Force

$PreviousLanHosts = $env:DJANGO_LAN_HOSTS
$PreviousTiandituSourceIP = $env:TIANDITU_DIRECT_SOURCE_IP
$PreviousTiandituInterfaceIndex = $env:TIANDITU_DIRECT_INTERFACE_INDEX
$PreviousTiandituDnsServers = $env:TIANDITU_DIRECT_DNS_SERVERS
try {
    $env:DJANGO_LAN_HOSTS = (@('127.0.0.1', 'localhost') + $LanAddresses) -join ','
    if ($TiandituDirectRoute) {
        $env:TIANDITU_DIRECT_SOURCE_IP = $TiandituDirectRoute.SourceIP
        $env:TIANDITU_DIRECT_INTERFACE_INDEX = [string]$TiandituDirectRoute.InterfaceIndex
        $env:TIANDITU_DIRECT_DNS_SERVERS = $TiandituDirectRoute.DnsServers
        Write-Host "Tianditu direct network: $($TiandituDirectRoute.SourceIP) (interface $($TiandituDirectRoute.InterfaceIndex); DNS $($TiandituDirectRoute.DnsServers))"
    }
    Write-Host 'Local: https://localhost:8000/login/'
    Write-Host "Mobile root CA (install this public certificate on each phone): $MobileRootCertificate"
    foreach ($LanAddress in $LanAddresses) {
        Write-Host "LAN login: https://${LanAddress}:8000/login/"
        Write-Host "LAN admin: https://${LanAddress}:8000/manage/"
        Write-Host "LAN mobile: https://${LanAddress}:8000/m/"
    }
    if ($LanAddresses.Count -gt 0) {
        Write-Host 'Install and trust the mobile root CA before opening the HTTPS link. The phone and this computer must be on the same network.'
    }
    if ($LanAddresses.Count -eq 0) {
        Write-Warning 'No active LAN IPv4 address found. Connect Ethernet/Wi-Fi and restart this script.'
    }
    & $PythonCommand manage.py runsslserver 0.0.0.0:8000 --certificate $CertificateFile --key $PrivateKeyFile --insecure
    $ServerExitCode = $LASTEXITCODE
} finally {
    $env:DJANGO_LAN_HOSTS = $PreviousLanHosts
    $env:TIANDITU_DIRECT_SOURCE_IP = $PreviousTiandituSourceIP
    $env:TIANDITU_DIRECT_INTERFACE_INDEX = $PreviousTiandituInterfaceIndex
    $env:TIANDITU_DIRECT_DNS_SERVERS = $PreviousTiandituDnsServers
}
exit $ServerExitCode
