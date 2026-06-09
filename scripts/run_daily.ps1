# AI-Pulse 日次バッチ: RSS 収集 + 関連カルテ fast 更新 + サイト再生成
# Task Scheduler 登録: 毎日 7:00
#   プログラム: powershell.exe
#   引数      : -NoProfile -ExecutionPolicy Bypass -File "<このファイルのフルパス>"
#
# .bat 版 (run_daily.bat) との差分:
#   - PS5.1 既定の CP932 文字化けを回避（UTF-8 で stdout/log を統一）
#   - %DATE% パース不要（Get-Date で確定）
#   - パス解決は $PSScriptRoot 相対（マルチバイトパスでも安定）

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'

$AiPulse   = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $AiPulse '.venv\Scripts\python.exe'
$LogsDir   = Join-Path $AiPulse '_logs'
$DateStr   = Get-Date -Format 'yyyyMMdd'
$LogPath   = Join-Path $LogsDir "daily_$DateStr.log"

if (-not (Test-Path -LiteralPath $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
}

$Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
Add-Content -LiteralPath $LogPath -Value "[$Stamp] 日次バッチ 開始" -Encoding UTF8

$Preflight = Join-Path $AiPulse 'scripts\refresh_notebooklm_auth.ps1'
if (Test-Path -LiteralPath $Preflight) {
    $Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -LiteralPath $LogPath -Value "[$Stamp] NotebookLM 認証 preflight 開始" -Encoding UTF8
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Preflight 2>&1 |
        Out-File -LiteralPath $LogPath -Append -Encoding UTF8
    $PreflightExit = $LASTEXITCODE
    $Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -LiteralPath $LogPath -Value "[$Stamp] NotebookLM 認証 preflight 終了 (exit $PreflightExit)" -Encoding UTF8
}

& $PythonExe (Join-Path $AiPulse 'tools\run_daily.py') 2>&1 |
    Out-File -LiteralPath $LogPath -Append -Encoding UTF8

$ExitCode = $LASTEXITCODE
$Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
Add-Content -LiteralPath $LogPath -Value "[$Stamp] 日次バッチ 終了 (exit $ExitCode)" -Encoding UTF8

exit $ExitCode
