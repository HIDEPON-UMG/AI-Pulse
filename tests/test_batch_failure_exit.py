"""日次・週次バッチの部分失敗を exit 0 に隠さない契約テスト。"""
from __future__ import annotations

import pytest

import tools.run_daily as run_daily
import tools.run_weekly as run_weekly


def test_run_daily_raises_after_notebooklm_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        run_daily.collect_rss,
        "collect_entities",
        lambda: {"added": [{"entity_id": "claude-opus"}]},
    )
    monkeypatch.setattr(
        run_daily.schema,
        "validate_store",
        lambda *_args: ([{"entity_id": "claude-opus"}], []),
    )
    monkeypatch.setattr(run_daily, "_fast_update", lambda _entity: (_ for _ in ()).throw(RuntimeError("auth expired")))
    monkeypatch.setattr(run_daily.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(run_daily.backfill_thumb, "backfill", lambda: None)
    monkeypatch.setattr(run_daily.generate_pages, "main", lambda: None)

    with pytest.raises(RuntimeError, match="カルテ更新失敗: 1 件"):
        run_daily.run_daily()


def test_run_weekly_raises_after_notebooklm_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        run_weekly.schema,
        "validate_store",
        lambda *_args: ([{"entity_id": "claude-opus"}], []),
    )
    monkeypatch.setattr(run_weekly, "_deep_update", lambda _entity: (_ for _ in ()).throw(RuntimeError("auth expired")))
    monkeypatch.setattr(run_weekly.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(run_weekly.generate_pages, "main", lambda: None)

    with pytest.raises(RuntimeError, match="週次カルテ更新失敗: 1 件"):
        run_weekly.run_weekly()
