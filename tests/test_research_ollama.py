"""Ollama カルテ更新の契約テスト。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.research_ollama as ro


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_update_entity_merges_ollama_payload_without_dropping_existing_columns(
    tmp_path: Path,
) -> None:
    entities_path = tmp_path / "entities.jsonl"
    events_path = tmp_path / "events.jsonl"
    entity = {
        "entity_id": "claude-opus",
        "name": "Claude Opus",
        "kind": "model",
        "domain": "language",
        "offering": "commercial",
        "vendor": "Anthropic",
        "category": "model",
        "snapshot_date": "2026-06-01",
        "positioning": "Anthropic の最上位 LLM",
        "overview": "古い overview",
        "comparison": {
            "cols": [
                {
                    "name": "Claude Opus",
                    "self": True,
                    "cells": {
                        "strength": "旧強み",
                        "context": "旧文脈",
                        "mm_in": "旧入力",
                        "mm_out": "旧出力",
                        "ecosystem": "旧連携",
                        "pricing": "旧価格",
                    },
                },
                {
                    "name": "GPT",
                    "cells": {
                        "strength": "競合強み",
                        "context": "競合文脈",
                        "mm_in": "競合入力",
                        "mm_out": "競合出力",
                        "ecosystem": "競合連携",
                        "pricing": "競合価格",
                    },
                },
            ]
        },
        "logo": {
            "path": "assets/service-icons/claude-opus.png",
            "fetched_at": "2026-06-08",
            "license_note": "test asset",
            "status": "verified",
        },
    }
    event = {
        "event_id": "e1",
        "entity_id": "claude-opus",
        "date": "2026-06-10",
        "category": "model",
        "event_type": "release",
        "headline": "Claude Opus update",
        "summary": "Claude Opus の更新内容。",
        "score": 80,
        "importance": "high",
        "source": "Anthropic",
        "source_tier": "T1",
    }
    _write_jsonl(entities_path, [entity])
    _write_jsonl(events_path, [event])

    def fake_generator(target: dict, recent_events: list[dict]) -> dict:
        assert target["entity_id"] == "claude-opus"
        assert recent_events == [event]
        return {
            "overview": "Ollama が生成した新しい overview。既存イベントだけを根拠にした説明です。",
            "cells": {
                "strength": ["長文脈", "高品質推論"],
                "context": "1M トークン級",
                "mm_in": "テキスト・画像",
                "mm_out": "テキスト",
                "ecosystem": "API と MCP",
                "pricing": "N/A",
            },
        }

    updated = ro.update_entity(
        entity,
        [event],
        entities_path=entities_path,
        events_path=events_path,
        generator=fake_generator,
    )

    assert updated["overview"].startswith("Ollama が生成")
    assert updated["logo"]["path"] == "assets/service-icons/claude-opus.png"
    cols = updated["comparison"]["cols"]
    assert cols[0]["name"] == "Claude Opus"
    assert cols[0]["cells"]["strength"] == ["長文脈", "高品質推論"]
    assert cols[1]["name"] == "GPT"
    assert cols[1]["cells"]["strength"] == "競合強み"
    persisted = [json.loads(line) for line in entities_path.read_text(encoding="utf-8").splitlines()]
    assert persisted[0]["overview"] == updated["overview"]


def test_update_entity_rejects_unknown_entity(tmp_path: Path) -> None:
    entities_path = tmp_path / "entities.jsonl"
    events_path = tmp_path / "events.jsonl"
    _write_jsonl(entities_path, [])
    _write_jsonl(events_path, [])

    with pytest.raises(Exception, match="未知の entity_id"):
        ro.update_entity(
            {"entity_id": "ghost"},
            [],
            entities_path=entities_path,
            events_path=events_path,
            generator=lambda *_args: {},
        )
