"""collect_rss の LLM 前重複排除契約テスト。

なぜ重要か:
  日次バッチは毎日同じ Google News RSS 候補を拾いやすい。既存記事との重複を
  store.ingest_events 後段で落とすだけだと、本文取得とローカル LLM 要約を済ませた
  後に捨てるため、GPU/VRAM と実行時間を無駄にする。

  既存 event の (entity_id, headline) と RSS item.title が一致するものは、本文を
  読む前に既読と判定できる。本テストは、その経路で fetch_article.extract と
  llm_hybrid.generate_event_extras が呼ばれないことを固定する。
"""
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
        "entity_id": "claude-opus",
        "name": "Claude Opus",
        "kind": "model",
        "domain": "language",
        "offering": "commercial",
        "vendor": "Anthropic",
        "category": "model",
        "snapshot_date": "2026-06-01",
        "positioning": "テスト対象",
    }


def _event(headline: str) -> dict:
    return {
        "event_id": "2026-06-01-claudeop-gem01",
        "entity_id": "claude-opus",
        "date": "2026-06-01",
        "category": "model",
        "event_type": "release",
        "headline": headline,
        "summary": "既存要約",
        "summary_points": ["既存要約ポイント1", "既存要約ポイント2", "既存要約ポイント3"],
        "rationale": {
            "impact": "既存イベントは開発者の利用判断に影響するためです。",
            "importance": "既存イベントは主要モデルの更新として重要であるためです。",
            "buzz": "既存イベントは利用者コミュニティで話題になりやすいためです。",
        },
        "score": 80,
        "importance": "high",
        "source": "Existing",
        "source_tier": "T2",
        "source_url": "https://example.com/existing",
    }


def test_existing_title_duplicate_is_skipped_before_fetch_and_llm(tmp_path, monkeypatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    _write_jsonl(data / "entities.jsonl", [_entity()])
    _write_jsonl(data / "events.jsonl", [_event("Repeated AI News")])

    monkeypatch.setattr(collect_rss, "DATA", data)
    monkeypatch.setattr(collect_rss.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        collect_rss,
        "_fetch_rss",
        lambda _query, num=5: [
            {
                "title": "  repeated   ai news  ",
                "link": "https://example.com/duplicate",
                "rss_summary": "既存記事",
                "date": "2026-06-08",
                "source_name": "Example",
                "source_url_hint": "https://example.com",
            },
            {
                "title": "Fresh AI News",
                "link": "https://example.com/fresh",
                "rss_summary": "新規記事",
                "date": "2026-06-08",
                "source_name": "Example",
                "source_url_hint": "https://example.com",
            },
        ],
    )

    fetched_links: list[str] = []
    llm_titles: list[str] = []

    def fake_extract(link: str) -> dict:
        fetched_links.append(link)
        if "duplicate" in link:
            raise AssertionError("既存 title 重複記事で本文取得が呼ばれた")
        return {
            "publisher_url": link,
            "publisher_name": "Example",
            "og_image": "",
            "text": "Fresh AI News reports that Claude Opus improved coding accuracy.",
        }

    def fake_generate_event_extras(_body: str, meta: dict) -> dict:
        llm_titles.append(meta["title"])
        return {
            "summary": "Claude Opusの新しい改善が報じられた。",
            "summary_points": [
                "Claude Opusの改善が報じられた。",
                "開発者向けの精度改善が中心である。",
                "既存ユーザーへの影響が見込まれる。",
            ],
            "rationale": {
                "impact": "開発者利用の判断に影響する改善であるためです。",
                "importance": "主要モデルの更新として継続的に追う必要があるためです。",
                "buzz": "開発者コミュニティの関心が高い話題であるためです。",
            },
            "score": 80,
            "importance": "high",
            "event_type": "release",
            "is_relevant": True,
        }

    monkeypatch.setattr(collect_rss.fetch_article, "extract", fake_extract)
    monkeypatch.setattr(collect_rss.llm_hybrid, "generate_event_extras", fake_generate_event_extras)
    monkeypatch.setattr(collect_rss.llm_hybrid, "translate_headline_ja", lambda headline, **_: headline)

    result = collect_rss.collect_entities(["claude-opus"])

    assert result["skipped_pre_dup"] == 1
    assert result["skipped_dup"] == 0
    assert len(result["added"]) == 1
    assert fetched_links == ["https://example.com/fresh"]
    assert llm_titles == ["Fresh AI News"]
