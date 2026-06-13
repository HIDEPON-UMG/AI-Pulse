from pathlib import Path


def test_publish_daily_tracks_repo_radar_data() -> None:
    """Repo Radar の公開 JSONL を日次公開の commit/push 対象に含める。"""
    script = Path("scripts/publish_daily.ps1").read_text(encoding="utf-8-sig")

    assert "'data\\repo_radar.jsonl'" in script


def test_run_daily_uses_separate_publish_log() -> None:
    """日次ログを公開プロセスへ共有せず、Add-Content のロック競合を避ける。"""
    script = Path("scripts/run_daily.ps1").read_text(encoding="utf-8-sig")
    publish_block = script.split("$Publish = Join-Path", maxsplit=1)[1]

    assert "$PublishLogPath" in publish_block
    assert "-File $Publish -LogPath $LogPath" not in publish_block
