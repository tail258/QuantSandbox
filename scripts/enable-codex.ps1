#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Run setup.cmd before configuring the QuantSandbox MCP server.'
}
$adapter = Join-Path $PSScriptRoot 'quantsandbox_mcp.py'
$directory = Join-Path $root '.codex'
$path = Join-Path $directory 'config.toml'
[string]$old = if (Test-Path -LiteralPath $path) { Get-Content -LiteralPath $path -Raw -Encoding utf8 } else { '' }
$begin = '# BEGIN QuantSandbox MCP (managed by scripts/enable-codex.ps1)'
$end = '# END QuantSandbox MCP'
$block = @"
$begin
[mcp_servers.quantsandbox]
command = $(ConvertTo-Json -Compress -InputObject $python)
args = ["-X", "utf8", $(ConvertTo-Json -Compress -InputObject $adapter)]
cwd = $(ConvertTo-Json -Compress -InputObject $root)
tool_timeout_sec = 120
$end
"@
$managed = [regex]::new("(?ms)^$([regex]::Escape($begin))\r?\n.*?^$([regex]::Escape($end))(?=\r?$)")
$legacy = [regex]::new('(?m)^\[mcp_servers\.quantsandbox\][ \t]*\r?\ncommand = [^\r\n]+\r?\nargs = [^\r\n]+\r?\ncwd = [^\r\n]+\r?\ntool_timeout_sec = 65[ \t]*(?=\r?$)')
$legacyMatch = $legacy.Match($old)
if ($managed.IsMatch($old)) {
    $updated = $managed.Replace($old, { param($match) $block }, 1)
} elseif ($legacyMatch.Success -and $legacyMatch.Value.Contains('.local\codex-mcp\quantsandbox_mcp.py')) {
    $updated = $legacy.Replace($old, { param($match) "$block`n`n" }, 1)
} elseif ($old -match '(?m)^\s*\[\s*mcp_servers\s*\.\s*["'']?quantsandbox\b') {
    Write-Warning "An existing QuantSandbox MCP configuration was preserved in $path."
    return
} else {
    $updated = if ($old.Trim()) { $old.TrimEnd() + "`n`n" + $block } else { $block }
}
if ($updated.TrimEnd() -cne $old.TrimEnd()) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    Set-Content -LiteralPath $path -Value $updated.TrimEnd() -Encoding utf8NoBOM
}
Write-Output "QuantSandbox MCP is configured for $root."
