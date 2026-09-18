#Requires -Version 7.0
param([int]$ApiPort = 8000, [int]$WebPort = 5173)
$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = '1'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$pythonExecutable = Join-Path $workspaceRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) { throw 'Run scripts/setup.ps1 first.' }
$runtimeDir = Join-Path $workspaceRoot '.local'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
foreach ($servicePort in @($ApiPort, $WebPort)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $servicePort -ErrorAction SilentlyContinue) {
        throw "Port $servicePort is occupied. Stop the existing service before starting another workspace."
    }
}
$apiProcess = $null
Push-Location $workspaceRoot
try {
    $env:QUANT_API_PORT = [string]$ApiPort
    $apiProcess = Start-Process -FilePath $pythonExecutable -ArgumentList @('-X','utf8','-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',[string]$ApiPort) -WorkingDirectory $workspaceRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir 'backend.stdout.log') -RedirectStandardError (Join-Path $runtimeDir 'backend.stderr.log')
    $apiReady = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($apiProcess.HasExited) { throw 'Backend failed to start. Read .local/backend.stderr.log.' }
        try { $null = Invoke-RestMethod "http://127.0.0.1:$ApiPort/api/health" -NoProxy -TimeoutSec 1; $apiReady = $true; break } catch { Start-Sleep -Milliseconds 300 }
    }
    if (-not $apiReady) { throw 'Backend startup timed out. Read .local/backend.stderr.log.' }
    Write-Host "QuantSandbox: http://localhost:$WebPort" -ForegroundColor Cyan
    Write-Host 'Press Ctrl+C to stop this workspace.'
    & npm.cmd run dev --prefix frontend -- --host 127.0.0.1 --port $WebPort --strictPort
} finally {
    if ($apiProcess -and -not $apiProcess.HasExited) {
        # Only terminate the process tree started by this invocation, including
        # an active research worker. Killing just uvicorn would orphan it.
        & taskkill.exe /PID $apiProcess.Id /T /F 2>$null | Out-Null
    }
    Pop-Location
}
