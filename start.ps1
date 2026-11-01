param([switch]$NoBrowser, [int]$Port = 8766)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$runtime = Join-Path $projectRoot '.local'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$url = "http://127.0.0.1:$Port"
try {
    $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2 -NoProxy
    if ($health.app -eq 'QuantSandbox' -and $health.workspace -eq $projectRoot) {
        if (-not $NoBrowser) { Start-Process $url }
        Write-Output "QuantSandbox: $url"
        exit 0
    }
} catch {}
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is occupied by another service. Use -Port with a free port."
}
$pythonExecutable = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) { throw 'Run setup.cmd first.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) { throw 'Run setup.cmd first to build the UI.' }
$server = Start-Process -FilePath $pythonExecutable -ArgumentList @('-X','utf8','-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',[string]$Port) -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'server.log') -RedirectStandardError (Join-Path $runtime 'server-error.log') -PassThru
$server.Id | Set-Content -LiteralPath (Join-Path $runtime "server-$Port.pid")
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 400
    try {
        $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 1 -NoProxy
        if ($health.app -eq 'QuantSandbox' -and $health.workspace -eq $projectRoot) {
            Write-Output "QuantSandbox: $url"
            if (-not $NoBrowser) { Start-Process $url }
            exit 0
        }
    } catch {}
    if ($server.HasExited) { break }
}
throw 'Service did not start. Read .local/server-error.log.'
