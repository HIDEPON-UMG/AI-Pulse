from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import collect_rss  # noqa: E402


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _entity() -> dict:
    return {
        "entity_id": "vera-rubin",
        "name": "NVIDIA Vera Rubin",
        "kind": "hardware",
        "domain": "compute",
        "offering": "commercial",
        "vendor": "NVIDIA",
        "category": "infra",
        "snapshot_date": "2026-06-01",
        "positioning": "テスト対象",
    }


def test_collect_entities_applies_editorial_lint_before_ingest(tmp_path, monkeypatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    _write_jsonl(data / "entities.jsonl", [_entity()])
    _write_jsonl(data / "events.jsonl", [])

    monkeypatch.setattr(collect_rss, "DATA", data)
    monkeypatch.setattr(collect_rss.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        collect_rss,
        "_fetch_rss",
        lambda _query, num=5: [{
            "title": "Nvidia CEO called to Senate hearing",
            "link": "https://example.com/nvidia",
            "rss_summary": "Nvidia CEO hearing",
            "date": "2026-06-08",
            "source_name": "Example",
            "source_url_hint": "https://example.com",
        }],
    )
    monkeypatch.setattr(
        collect_rss.fetch_article,
        "extract",
        lambda _link: {
            "publisher_url": "https://example.com/nvidia",
            "publisher_name": "Example",
            "og_image": "",
            "text": "Nvidia CEO was called to a US Senate hearing about export controls.",
        },
    )
    monkeypatch.setattr(
        collect_rss.llm_hybrid,
        "generate_event_extras",
        lambda _body, _meta: {
            "summary": "参議院聴聞会で画期的な議論が行われた。",
            "summary_points": [
                "参議院の聴聞会でNvidia CEOが証言を求められた。",
                "輸出規制をめぐる議論が続いている。",
                "市場関係者の注目が集まっている。",
            ],
            "rationale": {
                "importance": "画期的な規制イベントとして重要である。",
                "impact": "輸出規制に関する議論が事業に影響するためである。",
                "buzz": "上院聴聞会として投資家の関心を集めている。",
            },
            "score": 80,
            "importance": "high",
            "event_type": "regulation",
            "is_relevant": True,
        },
    )
    monkeypatch.setattr(collect_rss.llm_hybrid, "translate_headline_ja", lambda headline, **_: headline)

    result = collect_rss.collect_entities(["vera-rubin"])

    assert len(result["added"]) == 1
    ev = result["added"][0]
    assert "参議院" not in ev["summary"]
    assert "聴聞会" not in ev["summary"]
    assert "画期的" not in ev["summary"]
    assert "米上院公聴会" in ev["summary"]
    assert "注目される" in ev["summary"]
    assert ev["summary_points"][0].startswith("米上院公聴会で")
