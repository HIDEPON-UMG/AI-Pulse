"""日次・週次バッチのカルテ更新失敗境界の契約テスト。"""
from __future__ import annotations

import pytest

import tools.run_daily as run_daily
import tools.run_weekly as run_weekly


@pytest.fixture(autouse=True)
def _no_repo_radar_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """既存の日次バッチテストでは外部ソーシャル収集を止める。"""
    monkeypatch.setattr(run_daily, "_run_repo_radar_x_rss", lambda: None)
    monkeypatch.setattr(run_daily.collect_repo_radar, "collect", lambda: {
        "candidates": 0,
        "enriched": 0,
        "evaluated": 0,
        "skipped": 0,
        "degraded": 0,
        "ollama_errors": 0,
    })
    monkeypatch.setattr(run_daily, "_export_repo_radar_obsidian", lambda: None)
    monkeypatch.setattr(run_daily, "_run_buzzpost_x_rss", lambda: None)
    monkeypatch.setattr(run_daily.collect_buzz_posts, "collect", lambda: {
        "collected": 0,
        "written": 0,
        "degraded": 0,
    })


def test_run_daily_continues_after_ollama_carte_failure(
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
    monkeypatch.setattr(
        run_daily,
        "_fast_update",
        lambda _entity, _events: (_ for _ in ()).throw(RuntimeError("ollama down")),
    )
    monkeypatch.setattr(run_daily.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(run_daily.backfill_thumb, "backfill", lambda: None)
    monkeypatch.setattr(run_daily.generate_pages, "main", lambda: None)

    run_daily.run_daily()

    captured = capsys.readouterr()
    assert "カルテ更新失敗: 1 件" in captured.err
    assert "日次本線は完了" in captured.err


def test_run_daily_updates_added_entities_with_ollama(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        run_daily.collect_rss,
        "collect_entities",
        lambda: {"added": [{"entity_id": "claude-opus"}, {"entity_id": "gemini"}]},
    )
    monkeypatch.setattr(
        run_daily.schema,
        "validate_store",
        lambda *_args: ([{"entity_id": "claude-opus"}, {"entity_id": "gemini"}], []),
    )
    calls: list[tuple[str, list[dict]]] = []
    monkeypatch.setattr(
        run_daily,
        "_fast_update",
        lambda entity, events: calls.append((entity["entity_id"], events)),
    )
    monkeypatch.setattr(run_daily.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(run_daily.backfill_thumb, "backfill", lambda: None)
    monkeypatch.setattr(run_daily.generate_pages, "main", lambda: None)

    run_daily.run_daily()

    captured = capsys.readouterr()
    assert {eid for eid, _events in calls} == {"claude-opus", "gemini"}
    assert all(events for _eid, events in calls)
    assert "NotebookLM" not in captured.err
    assert "カルテ更新失敗:" not in captured.err


def test_run_daily_does_not_call_notebooklm_auth_preflight(
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
    monkeypatch.setattr(run_daily, "_fast_update", lambda _entity, _events: None)
    monkeypatch.setattr(run_daily.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(run_daily.backfill_thumb, "backfill", lambda: None)
    monkeypatch.setattr(run_daily.generate_pages, "main", lambda: None)

    run_daily.run_daily()

    captured = capsys.readouterr()
    assert "NotebookLM" not in captured.out
    assert "NotebookLM" not in captured.err
    assert "カルテ更新失敗:" not in captured.err


def test_run_daily_continues_after_repo_radar_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        run_daily.collect_rss,
        "collect_entities",
        lambda: {"added": [{"entity_id": "demo"}], "quality_audit_records": []},
    )
    monkeypatch.setattr(run_daily.quality_audit, "audit_records", lambda _records: {
        "audited": 0,
        "ok": 0,
        "warn": 0,
        "fail": 0,
        "errors": 0,
        "term_candidates": 0,
    })
    monkeypatch.setattr(
        run_daily.collect_repo_radar,
        "collect",
        lambda: (_ for _ in ()).throw(RuntimeError("repo radar down")),
    )
    monkeypatch.setattr(
        run_daily.schema,
        "validate_store",
        lambda *_args: ([{"entity_id": "demo"}], []),
    )
    monkeypatch.setattr(run_daily, "_fast_update", lambda _entity, _events: calls.append("carte"))
    monkeypatch.setattr(run_daily.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(run_daily.backfill_thumb, "backfill", lambda: calls.append("thumb"))
    monkeypatch.setattr(run_daily.generate_pages, "main", lambda: calls.append("pages"))

    run_daily.run_daily()

    assert calls == ["carte", "thumb", "pages"]


def test_run_weekly_raises_after_ollama_carte_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        run_weekly.schema,
        "validate_store",
        lambda *_args: ([{"entity_id": "claude-opus"}], []),
    )
    monkeypatch.setattr(run_weekly, "_deep_update", lambda _entity, _events: (_ for _ in ()).throw(RuntimeError("ollama down")))
    monkeypatch.setattr(run_weekly.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(run_weekly.generate_pages, "main", lambda: None)

    with pytest.raises(RuntimeError, match="週次カルテ更新失敗: 1 件"):
        run_weekly.run_weekly()
