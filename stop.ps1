param([int]$Port = 8766)
$ErrorActionPreference = 'Stop'
$pidFile = Join-Path $PSScriptRoot ".local\server-$Port.pid"
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Output 'No owned server PID file.'; exit 0 }
$serverProcessId = [int](Get-Content -LiteralPath $pidFile)
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$serverProcessId" -ErrorAction SilentlyContinue
$expectedPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if ($process -and $process.ExecutablePath -eq $expectedPython -and $process.CommandLine -match 'uvicorn backend.main:app' -and $process.CommandLine -match "--port $Port(\s|$)") {
    # Stop only this launcher process and its verified interpreter child.
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$serverProcessId" | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'uvicorn backend.main:app' -and $_.CommandLine -match "--port $Port(\s|$)" }
    foreach ($child in $children) { Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue }
    Stop-Process -Id $serverProcessId -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $pidFile
    Write-Output 'QuantSandbox stopped.'
} elseif (-not $process) {
    Remove-Item -LiteralPath $pidFile
    Write-Output 'Owned process already exited.'
} else { throw 'PID does not identify an owned QuantSandbox server; no process stopped.' }
