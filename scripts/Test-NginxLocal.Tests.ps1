. (Join-Path $PSScriptRoot 'nginx-local.ps1') -LoadOnly

Describe 'Nginx local LAN HTTPS configuration' {
    It 'quotes forward-slash certificate paths that contain spaces' {
        $config = Get-NginxConfigText -ProjectRoot 'C:\Selectrom Projects\selectrom'
        $config | Should Match 'ssl_certificate "C:/Selectrom Projects/selectrom/.certs/lan\.pem";'
        $config | Should Match 'ssl_certificate_key "C:/Selectrom Projects/selectrom/.certs/lan-key\.pem";'
    }

    It 'uses a forward-slash Nginx prefix that keeps spaces in the path' {
        $prefix = Get-NginxPrefix -NginxRoot 'C:\Selectrom Tools\nginx'
        $prefix | Should Be 'C:/Selectrom Tools/nginx/'
    }

    It 'rejects quote and newline characters in the project path' {
        $newlineMessage = ''
        try {
            Get-NginxConfigText -ProjectRoot "C:\selectrom`ninvalid"
        } catch {
            $newlineMessage = $_.Exception.Message
        }
        $newlineMessage | Should Match 'quote or newline'

        $quoteMessage = ''
        try {
            Get-NginxConfigText -ProjectRoot 'C:\selectrom"invalid'
        } catch {
            $quoteMessage = $_.Exception.Message
        }
        $quoteMessage | Should Match 'quote or newline'
    }

    It 'proxies HTTPS to the loopback Django server and forwards request headers' {
        $config = Get-NginxConfigText -ProjectRoot 'D:\selectrom'
        $config | Should Match 'listen 443 ssl;'
        $config | Should Match 'proxy_pass https://127\.0\.0\.1:8000;'
        $config | Should Match 'proxy_ssl_verify off;'
        $config | Should Match 'proxy_set_header Host \$http_host;'
        $config | Should Match 'proxy_set_header X-Real-IP \$remote_addr;'
        $config | Should Match 'proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;'
        $config | Should Match 'proxy_set_header X-Forwarded-Proto https;'
    }

    It 'explains when the Nginx executable is missing' {
        $root = Join-Path $TestDrive 'missing-nginx-project'
        New-Item -ItemType Directory -Path (Join-Path $root '.certs') -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $root '.certs\lan.pem') -Value 'cert'
        Set-Content -LiteralPath (Join-Path $root '.certs\lan-key.pem') -Value 'key'
        $message = ''
        try {
            Assert-NginxPrerequisites -ProjectRoot $root -NginxRoot (Join-Path $TestDrive 'missing-nginx')
        } catch {
            $message = $_.Exception.Message
        }
        $message | Should Match 'nginx\.exe'
    }

    It 'explains when the mkcert HTTPS certificate is missing' {
        $root = Join-Path $TestDrive 'missing-cert-project'
        $nginxRoot = Join-Path $TestDrive 'nginx-bin'
        New-Item -ItemType Directory -Path $root, $nginxRoot -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $nginxRoot 'nginx.exe') -Value 'placeholder'
        $message = ''
        try {
            Assert-NginxPrerequisites -ProjectRoot $root -NginxRoot $nginxRoot
        } catch {
            $message = $_.Exception.Message
        }
        $message | Should Match 'scripts\\start\.ps1'
    }

    It 'treats an empty nginx PID file as a stopped process' {
        $root = Join-Path $TestDrive 'empty-pid-nginx'
        $logs = Join-Path $root 'logs'
        New-Item -ItemType Directory -Path $logs -Force | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $logs 'nginx.pid'), '')
        $processId = Get-NginxProcessId -NginxRoot $root
        $processId | Should Be $null
    }
}
