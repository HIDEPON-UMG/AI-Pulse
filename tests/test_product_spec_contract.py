from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "spec.md"
ENTITIES = ROOT / "data" / "entities.jsonl"
EVENTS = ROOT / "data" / "events.jsonl"


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_product_spec_reflects_live_data_and_known_gaps() -> None:
    text = SPEC.read_text(encoding="utf-8")
    entities = _jsonl(ENTITIES)
    events = _jsonl(EVENTS)

    by_category: dict[str, int] = {}
    for entity in entities:
        category = entity["category"]
        by_category[category] = by_category.get(category, 0) + 1

    by_entity: dict[str, int] = {}
    for event in events:
        entity_id = event["entity_id"]
        by_entity[entity_id] = by_entity.get(entity_id, 0) + 1

    zero_event_entities = sorted(entity["entity_id"] for entity in entities if by_entity.get(entity["entity_id"], 0) == 0)
    headline_ja_count = sum(1 for event in events if event.get("headline_ja"))
    thumb_count = sum(1 for event in events if event.get("thumb"))

    assert "> **Status**: Constitution" in text
    assert f"{len(entities)} entities" in text
    assert f"{len(events)} events" in text
    for category, count in by_category.items():
        assert f"{category} {count}" in text
    for entity_id in zero_event_entities:
        assert entity_id in text
    assert f"`headline_ja` exists for {headline_ja_count} / {len(events)} events" in text
    assert f"`thumb` exists for {thumb_count} / {len(events)} events" in text


def test_product_spec_is_not_placeholder_or_vague_goal_statement() -> None:
    text = SPEC.read_text(encoding="utf-8")
    forbidden = [
        "Describe the stable user or operator outcome",
        "Primary workflow:",
        "Quality bar:",
        "Out of scope:",
        "- ...",
    ]
    for phrase in forbidden:
        assert phrase not in text

    required_phrases = [
        "Core / Why / What / How",
        "Feature / Test Traceability Matrix",
        "ChatGPT consult",
        "repo-local tests",
        "URL gate",
        "公開確認",
        "site/` の公開経路が未解明",
    ]
    for phrase in required_phrases:
        assert phrase in text


def test_product_spec_traceability_commands_reference_existing_checks() -> None:
    text = SPEC.read_text(encoding="utf-8")
    command_refs = sorted(set(re.findall(r"(tests/test_[A-Za-z0-9_]+\.py|tools/[A-Za-z0-9_]+\.py)", text)))
    assert command_refs, "spec must list concrete verification commands"
    missing = [ref for ref in command_refs if not (ROOT / ref).exists()]
    assert missing == []

    required_refs = {
        "tests/test_run_daily.py",
        "tests/test_quality_audit.py",
        "tests/test_generate.py",
        "tests/test_publish_daily.py",
        "tools/audit_urls.py",
    }
    assert required_refs <= set(command_refs)
