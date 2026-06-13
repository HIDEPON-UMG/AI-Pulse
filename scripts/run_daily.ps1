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

# ===== ネット到達性待ち (再起動直後のネット未確立で RSS 収集が空振りするのを防ぐ) =====
# 2026-06-11: Windows Update 自動再起動直後 (07:00 直前) にネット未確立のまま起動する
#   事故への耐性。待ちロジックは ~/bin/net_wait.py (socket.connect_ex 純 Python) に
#   集約し News-Grasp runner と共有する (netstat 不使用 / [[feedback_check_design_principles]]
#   §2 境界集約)。AI-Pulse は git fetch のような hard exit が無く、サイト再生成は
#   ローカルでも価値があるため、待ちがタイムアウトしても中断せず WARN して続行する
#   (News-Grasp runner は git fetch 必須なので abort する点が異なる)。
$NetWait = Join-Path $env:USERPROFILE 'bin\net_wait.py'
if (Test-Path -LiteralPath $NetWait) {
    $Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -LiteralPath $LogPath -Value "[$Stamp] ネット到達性待ち 開始 (github.com:443, max 10x30s)" -Encoding UTF8
    & $PythonExe $NetWait --host github.com --host api.github.com --port 443 --retries 10 --interval-sec 30 --connect-timeout-sec 5 2>&1 |
        Out-File -LiteralPath $LogPath -Append -Encoding UTF8
    $NetRc = $LASTEXITCODE
    $Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    if ($NetRc -ne 0) {
        Add-Content -LiteralPath $LogPath -Value "[$Stamp] WARN: ネット未確立 (rc=$NetRc) だが続行する" -Encoding UTF8
    } else {
        Add-Content -LiteralPath $LogPath -Value "[$Stamp] ネット到達性 OK" -Encoding UTF8
    }
}

# ===== Ollama 起動待ち (カルテ更新は NotebookLM ではなくローカル Ollama を使う) =====
$Ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if ($Ollama) {
    $Client = New-Object System.Net.Sockets.TcpClient
    try {
        $Connect = $Client.BeginConnect('127.0.0.1', 11434, $null, $null)
        $Ready = $Connect.AsyncWaitHandle.WaitOne(1000, $false)
        if ($Ready) {
            $Client.EndConnect($Connect)
        }
    } catch {
        $Ready = $false
    } finally {
        $Client.Close()
    }
    if (-not $Ready) {
        $Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
        Add-Content -LiteralPath $LogPath -Value "[$Stamp] Ollama 起動 開始" -Encoding UTF8
        Start-Process -FilePath $Ollama -ArgumentList 'serve' -WindowStyle Hidden | Out-Null
        for ($i = 1; $i -le 30; $i++) {
            Start-Sleep -Seconds 2
            $Client = New-Object System.Net.Sockets.TcpClient
            try {
                $Connect = $Client.BeginConnect('127.0.0.1', 11434, $null, $null)
                $Ready = $Connect.AsyncWaitHandle.WaitOne(1000, $false)
                if ($Ready) {
                    $Client.EndConnect($Connect)
                    break
                }
            } catch {
                $Ready = $false
            } finally {
                $Client.Close()
            }
        }
    }
    $Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    if ($Ready) {
        Add-Content -LiteralPath $LogPath -Value "[$Stamp] Ollama 到達性 OK" -Encoding UTF8
    } else {
        Add-Content -LiteralPath $LogPath -Value "[$Stamp] WARN: Ollama 未到達だが日次本線は続行する" -Encoding UTF8
    }
} else {
    $Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -LiteralPath $LogPath -Value "[$Stamp] WARN: ollama.exe が PATH に無いが日次本線は続行する" -Encoding UTF8
}

& $PythonExe (Join-Path $AiPulse 'tools\run_daily.py') 2>&1 |
    Out-File -LiteralPath $LogPath -Append -Encoding UTF8

$ExitCode = $LASTEXITCODE
$Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
Add-Content -LiteralPath $LogPath -Value "[$Stamp] 日次バッチ 終了 (exit $ExitCode)" -Encoding UTF8

if ($ExitCode -ne 0) {
    exit $ExitCode
}

$Publish = Join-Path $AiPulse 'scripts\publish_daily.ps1'
if (Test-Path -LiteralPath $Publish) {
    $Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -LiteralPath $LogPath -Value "[$Stamp] 日次公開 開始" -Encoding UTF8
    $PublishLogPath = Join-Path $LogsDir "publish_$DateStr.log"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Publish -LogPath $PublishLogPath
    $PublishExit = $LASTEXITCODE
    $Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -LiteralPath $LogPath -Value "[$Stamp] 日次公開 終了 (exit $PublishExit, log $PublishLogPath)" -Encoding UTF8
    exit $PublishExit
}

$Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
Add-Content -LiteralPath $LogPath -Value "[$Stamp] ERROR: publish_daily.ps1 が見つかりません" -Encoding UTF8
exit 1
