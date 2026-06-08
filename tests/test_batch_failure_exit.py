"""日次・週次バッチの NotebookLM 失敗境界の契約テスト。"""
from __future__ import annotations

import pytest

import tools.run_daily as run_daily
import tools.run_weekly as run_weekly


def test_run_daily_continues_after_notebooklm_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
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
    monkeypatch.setattr(run_daily.nb, "ensure_auth", lambda **_kwargs: None)
    monkeypatch.setattr(
        run_daily,
        "_fast_update",
        lambda _entity, **_kwargs: (_ for _ in ()).throw(RuntimeError("auth expired")),
    )
    monkeypatch.setattr(run_daily.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(run_daily.backfill_thumb, "backfill", lambda: None)
    monkeypatch.setattr(run_daily.generate_pages, "main", lambda: None)

    run_daily.run_daily()

    captured = capsys.readouterr()
    assert "カルテ更新失敗: 1 件" in captured.err
    assert "日次本線は完了" in captured.err


def test_run_daily_skips_carte_update_when_auth_preflight_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        run_daily.collect_rss,
        "collect_entities",
        lambda: {"added": [{"entity_id": "claude-opus"}, {"entity_id": "gemini"}]},
    )
    monkeypatch.setattr(
        run_daily.nb,
        "ensure_auth",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("refresh failed")),
    )
    calls: list[str] = []
    monkeypatch.setattr(run_daily, "_fast_update", lambda _entity, **_kwargs: calls.append("fast"))
    monkeypatch.setattr(run_daily.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(run_daily.backfill_thumb, "backfill", lambda: None)
    monkeypatch.setattr(run_daily.generate_pages, "main", lambda: None)

    run_daily.run_daily()

    captured = capsys.readouterr()
    assert calls == []
    assert "NotebookLM 認証 preflight 失敗" in captured.err
    assert "カルテ更新失敗: 2 件" in captured.err


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
