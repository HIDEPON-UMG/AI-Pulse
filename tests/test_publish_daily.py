from pathlib import Path


def test_publish_daily_tracks_repo_radar_data() -> None:
    """Repo Radar の公開 JSONL を日次公開の commit/push 対象に含める。"""
    script = Path("scripts/publish_daily.ps1").read_text(encoding="utf-8-sig")

    assert "'data\\repo_radar.jsonl'" in script


def test_publish_daily_tracks_buzzpost_data() -> None:
    """BuzzPost の公開データと stats を日次公開の commit/push 対象に含める。"""
    script = Path("scripts/publish_daily.ps1").read_text(encoding="utf-8-sig")

    assert "'data\\buzz_posts.jsonl'" in script
    assert "'data\\buzz_posts_stats.json'" in script


def test_publish_daily_does_not_treat_native_stderr_as_failure() -> None:
    """git push の通常 stderr 出力を PowerShell 例外として誤検出しない。"""
    script = Path("scripts/publish_daily.ps1").read_text(encoding="utf-8-sig")

    assert "$PreviousErrorActionPreference = $ErrorActionPreference" in script
    assert "$ErrorActionPreference = 'Continue'" in script
    assert "$ErrorActionPreference = $PreviousErrorActionPreference" in script


def test_run_daily_uses_separate_publish_log() -> None:
    """日次ログを公開プロセスへ共有せず、Add-Content のロック競合を避ける。"""
    script = Path("scripts/run_daily.ps1").read_text(encoding="utf-8-sig")
    publish_block = script.split("$Publish = Join-Path", maxsplit=1)[1]

    assert "$PublishLogPath" in publish_block
    assert "-File $Publish -LogPath $LogPath" not in publish_block


def test_publish_daily_verifies_public_freshness_after_push() -> None:
    """push 成功だけで完了扱いせず、公開 HTML の更新日まで確認する。"""
    script = Path("scripts/publish_daily.ps1").read_text(encoding="utf-8-sig")

    assert "tools\\check_public_freshness.py" in script
    assert "--expected-date" in script


def test_publish_daily_expected_date_comes_from_generated_site_meta() -> None:
    """公開 freshness は実行日ではなく、生成済み HTML の更新日メタを期待値にする。"""
    script = Path("scripts/publish_daily.ps1").read_text(encoding="utf-8-sig")
    freshness_block = script.split('"public freshness gate"', maxsplit=1)[0]

    assert "$ExpectedBuildDate = Get-GeneratedSiteBuildDate" in script
    assert "$ExpectedBuildDate = Get-Date" not in freshness_block


def test_publish_daily_runs_url_gate_before_no_change_skip() -> None:
    """既存公開 URL の link rot を、公開対象に変更が無い日でも検知する。"""
    script = Path("scripts/publish_daily.ps1").read_text(encoding="utf-8-sig")

    url_gate_index = script.index('Invoke-Native "URL gate"')

    assert url_gate_index < script.index("$PublishStatus = Invoke-GitCapture")
    assert url_gate_index < script.index("公開対象に変更なし")
