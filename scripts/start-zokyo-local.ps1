$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = Join-Path $RepoRoot "venv\Scripts\python.exe"
$AppUrl = "http://127.0.0.1:8000"
$HealthUrl = "$AppUrl/healthz"
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
    if (Test-LocalPort -Port 3306) { return }

    $service = Get-Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "mysql|mariadb" -or $_.DisplayName -match "mysql|mariadb" } |
        Select-Object -First 1
    if ($service) {
        if ($service.Status -ne "Running") {
            Start-Service -Name $service.Name
        }
        if (Wait-LocalPort -Port 3306 -TimeoutSeconds 30) { return }
    }

    if (Test-Path $MySqlExe) {
        $args = @()
        if (Test-Path $MySqlDefaults) {
            $args += "--defaults-file=$MySqlDefaults"
        }
        Start-Process -FilePath $MySqlExe `
            -ArgumentList $args `
            -WorkingDirectory (Split-Path $MySqlExe -Parent) `
            -WindowStyle Hidden
        if (Wait-LocalPort -Port 3306 -TimeoutSeconds 30) { return }
    }

    throw "Nao consegui iniciar o MySQL local na porta 3306. Abra o XAMPP e inicie o MySQL manualmente."
}

function Start-ZokyoFlask {
    if (Test-LocalPort -Port 8000) { return }
    if (-not (Test-Path $PythonExe)) {
        throw "Python do ambiente virtual nao encontrado em $PythonExe"
    }

    $env:FLASK_ENV = "development"
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
            $response = Invoke-WebRequest -UseBasicParsing $HealthUrl -TimeoutSec 3
            if ($response.StatusCode -lt 500) { return }
        } catch {
            Start-Sleep -Milliseconds 700
        }
    }
    throw "O Zokyo nao respondeu em $HealthUrl. Veja logs/zokyo-local.err.log."
}

Set-Location $RepoRoot
Start-LocalMySql
Start-ZokyoFlask
Wait-ZokyoReady
Start-Process $AppUrl
