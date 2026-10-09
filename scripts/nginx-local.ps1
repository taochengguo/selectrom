[CmdletBinding()]
param(
    [ValidateSet('Start', 'Test', 'Reload', 'Stop')]
    [string]$Action = 'Start',
    [switch]$LoadOnly
)

$ErrorActionPreference = 'Stop'
$script:ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Get-NginxConfigText {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)

    if ($ProjectRoot.Contains('"') -or $ProjectRoot.Contains("`r") -or $ProjectRoot.Contains("`n")) {
        throw 'Project path contains a quote or newline that cannot be represented safely in nginx.conf.'
    }

    $nginxProjectPath = $ProjectRoot.TrimEnd('\', '/') -replace '\\', '/'
    $template = @'
worker_processes 1;
error_log logs/error.log info;
pid logs/nginx.pid;

events {
    worker_connections 1024;
}

http {
    access_log logs/access.log;
    client_max_body_size 25m;

    server {
        listen 443 ssl;
        server_name _;

        ssl_certificate "__PROJECT_ROOT__/.certs/lan.pem";
        ssl_certificate_key "__PROJECT_ROOT__/.certs/lan-key.pem";
        ssl_protocols TLSv1.2 TLSv1.3;

        location / {
            proxy_pass https://127.0.0.1:8000;
            proxy_ssl_verify off;
            proxy_ssl_server_name on;
            proxy_ssl_name localhost;

            proxy_set_header Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
            proxy_read_timeout 120s;
        }
    }
}
'@
    return $template.Replace('__PROJECT_ROOT__', $nginxProjectPath)
}

function Assert-NginxPrerequisites {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][string]$NginxRoot
    )

    $nginxExecutable = Join-Path $NginxRoot 'nginx.exe'
    if (-not (Test-Path -LiteralPath $nginxExecutable -PathType Leaf)) {
        throw "Nginx was not found at '$nginxExecutable'. Download the official Windows archive from https://nginx.org/en/download.html and extract nginx.exe into .tools\nginx\."
    }

    $certificatePath = Join-Path $ProjectRoot '.certs\lan.pem'
    $privateKeyPath = Join-Path $ProjectRoot '.certs\lan-key.pem'
    if (-not (Test-Path -LiteralPath $certificatePath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $privateKeyPath -PathType Leaf)) {
        throw "mkcert HTTPS files are missing. Start the Django service with .\scripts\start.ps1 first; it creates '$certificatePath' and '$privateKeyPath'."
    }

    return $nginxExecutable
}

function Get-NginxPrefix {
    param([Parameter(Mandatory = $true)][string]$NginxRoot)
    return ($NginxRoot.TrimEnd('\', '/') -replace '\\', '/') + '/'
}

function Initialize-NginxConfig {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][string]$NginxRoot
    )

    $confDirectory = Join-Path $NginxRoot 'conf'
    $logsDirectory = Join-Path $NginxRoot 'logs'
    New-Item -ItemType Directory -Path $confDirectory, $logsDirectory -Force | Out-Null

    $configPath = Join-Path $confDirectory 'selectrom.conf'
    $configText = Get-NginxConfigText -ProjectRoot $ProjectRoot
    $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($configPath, $configText, $utf8WithoutBom)
    return $configPath
}

function Get-NginxProcessId {
    param([Parameter(Mandatory = $true)][string]$NginxRoot)

    $pidPath = Join-Path $NginxRoot 'logs\nginx.pid'
    if (-not (Test-Path -LiteralPath $pidPath -PathType Leaf)) {
        return $null
    }

    $pidText = Get-Content -LiteralPath $pidPath -Raw -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($pidText)) {
        return $null
    }

    $pidValue = 0
    if (-not [int]::TryParse($pidText.Trim(), [ref]$pidValue)) {
        return $null
    }
    return $pidValue
}

function Test-NginxProcessOwned {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][string]$NginxExecutable
    )

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) {
        return $false
    }

    try {
        return [string]::Equals($process.Path, $NginxExecutable, [StringComparison]::OrdinalIgnoreCase)
    } catch {
        return $false
    }
}

function Invoke-NginxLocalAction {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('Start', 'Test', 'Reload', 'Stop')][string]$Action,
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][string]$NginxRoot
    )

    $nginxExecutable = Assert-NginxPrerequisites -ProjectRoot $ProjectRoot -NginxRoot $NginxRoot
    $null = Initialize-NginxConfig -ProjectRoot $ProjectRoot -NginxRoot $NginxRoot
    $commonArguments = @('-p', (Get-NginxPrefix -NginxRoot $NginxRoot), '-c', 'conf/selectrom.conf')

    if ($Action -eq 'Test') {
        & $nginxExecutable @commonArguments -t
        if ($LASTEXITCODE -ne 0) {
            throw "nginx -t failed with exit code $LASTEXITCODE. Review '$NginxRoot\logs\error.log'."
        }
        return
    }

    $processId = Get-NginxProcessId -NginxRoot $NginxRoot
    $processIsRunning = $processId -and (Test-NginxProcessOwned -ProcessId $processId -NginxExecutable $nginxExecutable)
    if ($processId -and -not $processIsRunning) {
        Remove-Item -LiteralPath (Join-Path $NginxRoot 'logs\nginx.pid') -Force -ErrorAction SilentlyContinue
        $processId = $null
    }

    if ($Action -eq 'Start') {
        if ($processIsRunning) {
            throw "Nginx is already running with PID $processId. Use -Action Reload to apply the current configuration."
        }
        $listener = Get-NetTCPConnection -LocalPort 443 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($listener) {
            throw "TCP port 443 is already in use by PID $($listener.OwningProcess). Stop that service or change its port before starting Nginx."
        }

        & $nginxExecutable @commonArguments -t
        if ($LASTEXITCODE -ne 0) {
            throw "nginx -t failed with exit code $LASTEXITCODE. Review '$NginxRoot\logs\error.log'."
        }

        $startArguments = @('-p', ('"{0}"' -f (Get-NginxPrefix -NginxRoot $NginxRoot)), '-c', 'conf/selectrom.conf')
        Start-Process -FilePath $nginxExecutable -ArgumentList $startArguments -WindowStyle Hidden | Out-Null
        $startedProcessId = $null
        for ($attempt = 0; $attempt -lt 12; $attempt++) {
            Start-Sleep -Milliseconds 250
            $startedProcessId = Get-NginxProcessId -NginxRoot $NginxRoot
            if ($startedProcessId -and (Test-NginxProcessOwned -ProcessId $startedProcessId -NginxExecutable $nginxExecutable)) {
                break
            }
        }
        if (-not $startedProcessId -or -not (Test-NginxProcessOwned -ProcessId $startedProcessId -NginxExecutable $nginxExecutable)) {
            $logTail = if (Test-Path -LiteralPath (Join-Path $NginxRoot 'logs\error.log')) {
                (Get-Content -LiteralPath (Join-Path $NginxRoot 'logs\error.log') -Tail 20 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
            } else {
                'No error log was created.'
            }
            throw "Nginx did not start. Review '$NginxRoot\logs\error.log'. $logTail"
        }
        Write-Host "Nginx is listening for HTTPS on port 443 (PID $startedProcessId). Open https://<computer-LAN-IP>/"
        return
    }

    if (-not $processIsRunning) {
        if ($Action -eq 'Stop') {
            Write-Host 'Nginx is already stopped.'
            return
        }
        throw 'Nginx is not running. Start it with -Action Start before reloading.'
    }

    $signal = if ($Action -eq 'Reload') { 'reload' } else { 'quit' }
    & $nginxExecutable @commonArguments -s $signal
    if ($LASTEXITCODE -ne 0) {
        throw "Nginx $($Action.ToLowerInvariant()) failed with exit code $LASTEXITCODE. Review '$NginxRoot\logs\error.log'."
    }
    Write-Host "Nginx $($Action.ToLowerInvariant()) signal sent."
}

if (-not $LoadOnly) {
    try {
        $nginxRoot = Join-Path $script:ProjectRoot '.tools\nginx'
        Invoke-NginxLocalAction -Action $Action -ProjectRoot $script:ProjectRoot -NginxRoot $nginxRoot
    } catch {
        $errorMessage = if ($_.Exception -and $_.Exception.Message) { $_.Exception.Message } else { $_.ToString() }
        Write-Error -Message $errorMessage -ErrorAction Continue
        exit 1
    }
}
