from __future__ import annotations

from tools import run_daily


def test_run_daily_calls_quality_audit_before_carte_update(monkeypatch):
    calls: list[str] = []
    event = {"event_id": "e1", "entity_id": "demo"}
    audit_records = [{"event": event, "article_text": "本文"}]

    monkeypatch.setattr(
        run_daily.collect_rss,
        "collect_entities",
        lambda: {"added": [event], "quality_audit_records": audit_records},
    )
    monkeypatch.setattr(
        run_daily.quality_audit,
        "audit_records",
        lambda records: calls.append(f"audit:{len(records)}") or {
            "audited": len(records),
            "ok": 1,
            "warn": 0,
            "fail": 0,
            "errors": 0,
            "term_candidates": 0,
        },
    )
    monkeypatch.setattr(
        run_daily.schema,
        "validate_store",
        lambda _entities, _events: ([{"entity_id": "demo"}], []),
    )
    monkeypatch.setattr(run_daily, "_fast_update", lambda entity: calls.append("carte"))
    monkeypatch.setattr(run_daily.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(run_daily.backfill_thumb, "backfill", lambda: calls.append("thumb"))
    monkeypatch.setattr(run_daily.generate_pages, "main", lambda: calls.append("pages"))

    run_daily.run_daily()

    assert calls == ["audit:1", "carte", "thumb", "pages"]
