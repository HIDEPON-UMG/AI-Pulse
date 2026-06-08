$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$AiPulse = Split-Path -Parent $PSScriptRoot
$NotebookLm = Join-Path $env:USERPROFILE '.claude\tools\notebooklm-py\.venv\Scripts\notebooklm.exe'
$LogsDir = Join-Path $AiPulse '_logs'
$DateStr = Get-Date -Format 'yyyyMMdd'
$LogPath = Join-Path $LogsDir "notebooklm_auth_$DateStr.log"

if (-not (Test-Path -LiteralPath $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
}

$Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
Add-Content -LiteralPath $LogPath -Value "[$Stamp] refresh start" -Encoding UTF8

& $NotebookLm auth refresh --quiet 2>&1 |
    Out-File -LiteralPath $LogPath -Append -Encoding UTF8

$ExitCode = $LASTEXITCODE
if ($ExitCode -ne 0) {
    $Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -LiteralPath $LogPath -Value "[$Stamp] refresh failed; running auth check --test" -Encoding UTF8
    & $NotebookLm auth check --test 2>&1 |
        Out-File -LiteralPath $LogPath -Append -Encoding UTF8
}

$Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
Add-Content -LiteralPath $LogPath -Value "[$Stamp] refresh end exit=$ExitCode" -Encoding UTF8
exit $ExitCode
