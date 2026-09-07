$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = Join-Path $RepoRoot "venv\Scripts\python.exe"
$AppUrl = "http://127.0.0.1:8000"
$HealthUrl = "$AppUrl/healthz"
$ReadyUrl = "$AppUrl/readyz"
$DjTechUrl = "http://127.0.0.1:5500"
$DjTechDir = Join-Path $RepoRoot "dj-tech"
$LogDir = Join-Path $RepoRoot "logs"
$MySqlExe = "C:\xampp\mysql\bin\mysqld.exe"
$MySqlDefaults = "C:\xampp\mysql\bin\my.ini"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

function Test-LocalPort {
    param([int]$Port)
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Wait-LocalPort {
    param([int]$Port, [int]$TimeoutSeconds = 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-LocalPort -Port $Port) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Start-LocalMySql {
    if (Test-LocalPort -Port 3306) {
        Write-Host "MySQL ja esta rodando em 127.0.0.1:3306"
        return
    }

    $service = Get-Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "mysql|mariadb" -or $_.DisplayName -match "mysql|mariadb" } |
        Select-Object -First 1
    if ($service) {
        if ($service.Status -ne "Running") {
            Write-Host "Iniciando servico $($service.Name)..."
            Start-Service -Name $service.Name
        }
        if (Wait-LocalPort -Port 3306 -TimeoutSeconds 30) {
            Write-Host "MySQL pronto em 127.0.0.1:3306"
            return
        }
    }

    if (Test-Path $MySqlExe) {
        Write-Host "Iniciando MySQL local pelo XAMPP..."
        $args = @()
        if (Test-Path $MySqlDefaults) {
            $args += "--defaults-file=$MySqlDefaults"
        }
        Start-Process -FilePath $MySqlExe `
            -ArgumentList $args `
            -WorkingDirectory (Split-Path $MySqlExe -Parent) `
            -WindowStyle Hidden
        if (Wait-LocalPort -Port 3306 -TimeoutSeconds 30) {
            Write-Host "MySQL pronto em 127.0.0.1:3306"
            return
        }
    }

    throw "Nao consegui iniciar o MySQL local na porta 3306. Abra o XAMPP e inicie o MySQL manualmente."
}

function Start-ZokyoFlask {
    if (Test-LocalPort -Port 8000) {
        Write-Host "Zokyo ja esta rodando em $AppUrl"
        return
    }
    if (-not (Test-Path $PythonExe)) {
        throw "Python do ambiente virtual nao encontrado em $PythonExe"
    }

    $env:FLASK_ENV = "development"
    Write-Host "Iniciando painel Zokyo em $AppUrl..."
    Start-Process -FilePath $PythonExe `
        -ArgumentList @("-m", "flask", "--app", "wsgi:app", "run", "--host", "127.0.0.1", "--port", "8000") `
        -WorkingDirectory $RepoRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir "zokyo-local.out.log") `
        -RedirectStandardError (Join-Path $LogDir "zokyo-local.err.log")
}

function Wait-ZokyoReady {
    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-WebRequest -UseBasicParsing $HealthUrl -TimeoutSec 3
            $ready = Invoke-WebRequest -UseBasicParsing $ReadyUrl -TimeoutSec 3
            if ($health.StatusCode -eq 200 -and $ready.StatusCode -eq 200) {
                Write-Host "Zokyo pronto: $HealthUrl e $ReadyUrl OK"
                return
            }
        } catch {
            Start-Sleep -Milliseconds 700
        }
    }
    throw "O Zokyo nao ficou pronto em $ReadyUrl. Veja logs/zokyo-local.err.log."
}

function Start-DjTechSite {
    if (Test-LocalPort -Port 5500) {
        Write-Host "Site DJ Tech ja esta rodando em $DjTechUrl"
        return
    }
    if (-not (Test-Path $PythonExe)) {
        throw "Python do ambiente virtual nao encontrado em $PythonExe"
    }
    if (-not (Test-Path (Join-Path $DjTechDir "server.py"))) {
        throw "Servidor do site DJ Tech nao encontrado em $DjTechDir"
    }

    Write-Host "Iniciando site DJ Tech em $DjTechUrl..."
    $env:PANEL_API = $AppUrl
    $env:HOST = "127.0.0.1"
    $env:PORT = "5500"
    Start-Process -FilePath $PythonExe `
        -ArgumentList @("server.py") `
        -WorkingDirectory $DjTechDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir "dj-tech-local.out.log") `
        -RedirectStandardError (Join-Path $LogDir "dj-tech-local.err.log")
    if (-not (Wait-LocalPort -Port 5500 -TimeoutSeconds 20)) {
        throw "O site DJ Tech nao subiu na porta 5500. Veja logs/dj-tech-local.err.log."
    }
    Write-Host "Site DJ Tech pronto em $DjTechUrl"
}

Set-Location $RepoRoot
Start-LocalMySql
Start-ZokyoFlask
Wait-ZokyoReady
Start-DjTechSite
Start-Process $AppUrl
Start-Process $DjTechUrl
