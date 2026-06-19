# AI-Pulse 日次公開: 生成済みデータ/サイトを commit して origin へ push する

param(
    [string]$LogPath = "",
    [switch]$DryRun,
    [switch]$SkipAudit
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'

$AiPulse = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $AiPulse '.venv\Scripts\python.exe'
$DateStr = Get-Date -Format 'yyyyMMdd'

if ([string]::IsNullOrWhiteSpace($LogPath)) {
    $LogsDir = Join-Path $AiPulse '_logs'
    if (-not (Test-Path -LiteralPath $LogsDir)) {
        New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
    }
    $LogPath = Join-Path $LogsDir "publish_$DateStr.log"
}

function Write-Log {
    param([string]$Message)
    $Stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -LiteralPath $LogPath -Value "[$Stamp] $Message" -Encoding UTF8
}

function Invoke-Native {
    param(
        [string]$Step,
        [string]$FilePath,
        [string[]]$Arguments
    )
    Write-Log "$Step 開始: $FilePath $($Arguments -join ' ')"
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $Output = & $FilePath @Arguments 2>&1
        $Code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }
    if ($Output) {
        $Output | ForEach-Object {
            Add-Content -LiteralPath $LogPath -Value $_ -Encoding UTF8
        }
    }
    Write-Log "$Step 終了 (exit $Code)"
    if ($Code -ne 0) {
        throw "$Step failed (exit $Code)"
    }
}

function Invoke-GitCapture {
    param([string[]]$Arguments)
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $Output = & git @Arguments 2>&1
        $Code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }
    if ($Code -ne 0) {
        if ($Output) {
            $Output | ForEach-Object {
                Add-Content -LiteralPath $LogPath -Value $_ -Encoding UTF8
            }
        }
        throw "git $($Arguments -join ' ') failed (exit $Code)"
    }
    return $Output
}

Set-Location -LiteralPath $AiPulse

try {
    Write-Log "日次公開 開始 dry_run=$DryRun skip_audit=$SkipAudit"

    $Git = (Get-Command git -ErrorAction Stop).Source
    if (-not (Test-Path -LiteralPath $PythonExe)) {
        throw "python not found: $PythonExe"
    }

    # GitHub Pages は push 後の Actions で site/ を再生成する。site/ は gitignore 対象なので commit しない。
    $Targets = @(
        'data\events.jsonl',
        'data\entities.jsonl',
        'data\repo_radar.jsonl',
        'data\buzz_posts.jsonl',
        'data\buzz_posts_stats.json'
    )

    if (-not $DryRun -and -not $SkipAudit) {
        Invoke-Native "URL gate" $PythonExe @('tools\audit_urls.py', '--gate')
    }

    $PublishStatus = Invoke-GitCapture (@('status', '--porcelain', '--') + $Targets)

    if (-not $PublishStatus) {
        Write-Log "公開対象に変更なし。commit/push をスキップ"
        exit 0
    }

    Write-Log "公開対象の変更を検出"
    $PublishStatus | ForEach-Object {
        Add-Content -LiteralPath $LogPath -Value $_ -Encoding UTF8
    }

    if ($DryRun) {
        if ($SkipAudit) {
            Write-Log "DRYRUN: audit_urls --gate は SkipAudit 指定により省略"
        } else {
            Write-Log "DRYRUN: audit_urls --gate を実行予定"
        }
        Write-Log "DRYRUN: git add / commit / push / remote HEAD 照合を実行予定"
        exit 0
    }

    Invoke-Native "git add" $Git (@('add', '--') + $Targets)

    & git diff --cached --quiet -- $Targets
    $DiffCode = $LASTEXITCODE
    if ($DiffCode -eq 0) {
        Write-Log "staged 変更なし。commit/push をスキップ"
        exit 0
    }
    if ($DiffCode -ne 1) {
        throw "git diff --cached --quiet failed (exit $DiffCode)"
    }

    $Branch = (Invoke-GitCapture @('rev-parse', '--abbrev-ref', 'HEAD') | Select-Object -First 1)
    if ([string]::IsNullOrWhiteSpace($Branch) -or $Branch -eq 'HEAD') {
        throw "push 先ブランチを特定できません: $Branch"
    }

    $Message = "chore: daily update $DateStr"
    Invoke-Native "git commit" $Git @('commit', '-m', $Message)
    Invoke-Native "git push" $Git @('push', 'origin', $Branch)

    $LocalHead = (Invoke-GitCapture @('rev-parse', 'HEAD') | Select-Object -First 1)
    $RemoteLine = (Invoke-GitCapture @('ls-remote', 'origin', "refs/heads/$Branch") | Select-Object -First 1)
    $RemoteHead = ($RemoteLine -split '\s+')[0]
    if ($LocalHead -ne $RemoteHead) {
        throw "push 後の remote HEAD 不一致: local=$LocalHead remote=$RemoteHead"
    }

    $ExpectedBuildDate = Get-Date -Format 'yyyy-MM-dd'
    Invoke-Native "public freshness gate" $PythonExe @(
        'tools\check_public_freshness.py',
        '--expected-date', $ExpectedBuildDate
    )

    Write-Log "日次公開 完了: $Branch $LocalHead"
    exit 0
} catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    exit 1
}
