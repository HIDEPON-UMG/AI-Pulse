from __future__ import annotations

from datetime import datetime

from tools import quality_audit


def _event() -> dict:
    return {
        "event_id": "2026-06-08-demo-gem01",
        "entity_id": "demo",
        "source_url": "https://example.com/news",
        "headline": "Demo headline",
        "headline_ja": "デモ見出し",
        "summary": "デモ要約",
        "summary_points": ["本文に基づく要点"],
        "rationale": {
            "importance": "本文の重要な変化を説明している。",
            "impact": "影響範囲を本文に基づいて説明している。",
            "buzz": "話題性を本文に基づいて説明している。",
        },
    }


def test_audit_records_writes_quality_log_and_term_candidates(tmp_path, monkeypatch):
    monkeypatch.setattr(quality_audit.config, "QUALITY_AUDIT_ENABLED", True)
    monkeypatch.setattr(quality_audit.config, "QUALITY_AUDIT_MODEL", "gemini-2.5-flash-lite")
    event = _event()
    records = [quality_audit.build_audit_record(event, "記事本文")]

    def fake_audit(article_text: str, audited_event: dict) -> dict:
        assert article_text == "記事本文"
        assert audited_event["event_id"] == event["event_id"]
        return {
            "status": "warn",
            "issues": [{
                "category": "translation",
                "severity": "mid",
                "field": "headline_ja",
                "evidence": "不自然な訳語",
                "suggestion": "自然な訳語にする",
            }],
            "term_candidates": [{
                "bad": "聴聞会",
                "good": "公聴会",
                "reason": "米議会文脈では公聴会が自然",
                "kind": "phrase",
            }],
            "notes": "辞書候補あり",
        }

    stats = quality_audit.audit_records(
        records,
        audit_fn=fake_audit,
        log_dir=tmp_path,
        now=datetime(2026, 6, 8, 7, 0, 0),
    )

    assert stats["audited"] == 1
    assert stats["warn"] == 1
    assert stats["term_candidates"] == 1
    assert (tmp_path / "quality_audit_20260608.jsonl").exists()
    candidates = (tmp_path / "editorial_terms_candidates_20260608.jsonl").read_text(
        encoding="utf-8"
    )
    assert '"event_id": "2026-06-08-demo-gem01"' in candidates
    assert '"bad": "聴聞会"' in candidates


def test_audit_records_logs_errors_without_raising(tmp_path, monkeypatch):
    monkeypatch.setattr(quality_audit.config, "QUALITY_AUDIT_ENABLED", True)
    records = [quality_audit.build_audit_record(_event(), "記事本文")]

    def broken_audit(_article_text: str, _event: dict) -> dict:
        raise RuntimeError("API unavailable")

    stats = quality_audit.audit_records(
        records,
        audit_fn=broken_audit,
        log_dir=tmp_path,
        now=datetime(2026, 6, 8, 7, 0, 0),
    )

    assert stats["audited"] == 1
    assert stats["errors"] == 1
    log_text = (tmp_path / "quality_audit_20260608.jsonl").read_text(encoding="utf-8")
    assert '"status": "error"' in log_text
    assert "API unavailable" in log_text
