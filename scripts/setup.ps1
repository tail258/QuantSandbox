#Requires -Version 7.0
param([switch]$MarketData, [string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = '1'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
Push-Location $workspaceRoot
try {
    if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
        & $Python -X utf8 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 or newer is required.' }
    }
    & ./.venv/Scripts/python.exe -X utf8 -m pip install -r requirements-dev.txt -c requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    if ($MarketData) {
        & ./.venv/Scripts/python.exe -X utf8 -m pip install -r requirements-market.txt -c requirements-lock.txt
        if ($LASTEXITCODE -ne 0) { throw 'Market provider installation failed.' }
    }
    & npm.cmd ci --prefix frontend
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    Write-Host 'Ready. Run: pwsh -File scripts/dev.ps1' -ForegroundColor Cyan
} finally { Pop-Location }
