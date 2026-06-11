"""Ollama ベースの L1 カルテ更新。

NotebookLM の外部 research / Google 認証に依存せず、AI-Pulse が採用済みの
events.jsonl と既存 entity 情報だけを根拠にカルテを更新する。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import llm_local  # noqa: E402
import schema  # noqa: E402
import store  # noqa: E402

DATA = ROOT / "data"


def update_entity(
    entity: dict,
    events: list[dict],
    *,
    entities_path=None,
    events_path=None,
    generator=llm_local.generate_carte_fields,
) -> dict:
    """1 entity のカルテを Ollama 生成差分で更新して永続化する。"""
    entities_path = Path(entities_path or DATA / "entities.jsonl")
    events_path = Path(events_path or DATA / "events.jsonl")
    entities, all_events = schema.validate_store(entities_path, events_path)
    target_id = entity["entity_id"]
    by_id = {item["entity_id"]: item for item in entities}
    if target_id not in by_id:
        raise schema.SchemaError(f"Ollama carte update: 未知の entity_id={target_id!r}")

    target = by_id[target_id]
    source_events = events or [ev for ev in all_events if ev["entity_id"] == target_id]
    source_events = sorted(source_events, key=lambda ev: ev.get("date", ""), reverse=True)
    payload = generator(target, source_events)
    _merge_payload(target, payload)
    target["confidence"] = recalculate_confidence(target, source_events)
    schema.validate_entity(target)
    store.write_entities(entities_path, entities)
    return target


def recalculate_confidence(entity: dict, source_events: list[dict]) -> dict:
    """採用済み event と entity 内 URL から「裏取り率」用 confidence を再計算する。"""
    asserted = 0
    speculated = len((entity.get("modules") or {}).get("future") or [])
    unverified = 0

    for ev in source_events:
        has_url = bool(ev.get("source_url"))
        if ev.get("source_tier") in {"T1", "T2"} and has_url:
            asserted += 1
        else:
            unverified += 1

    for item in _iter_history_items(entity):
        if item.get("url"):
            asserted += 1
        else:
            unverified += 1

    unverified += _self_comparison_cell_count(entity)
    if asserted + speculated + unverified == 0:
        unverified = 1
    return {"asserted": asserted, "speculated": speculated, "unverified": unverified}


def _merge_payload(entity: dict, payload: dict) -> None:
    """Ollama payload を既存 entity にマージする。競合列や logo は保持する。"""
    entity["overview"] = payload["overview"].strip()
    cells = payload["cells"]
    axes = schema.LENS_AXES[entity["category"]]
    axis_keys = [axis["key"] for axis in axes]
    existing_cmp = entity.get("comparison") or {}
    existing_cols = list(existing_cmp.get("cols") or [])
    self_col = _find_self_col(entity, existing_cols)
    normalized_cells = {key: cells[key] for key in axis_keys}
    if self_col is None:
        existing_cols.insert(
            0,
            {"name": entity["name"], "self": True, "cells": normalized_cells},
        )
    else:
        self_col["self"] = True
        self_col["cells"].update(normalized_cells)
    entity["comparison"] = {"cols": existing_cols}


def _find_self_col(entity: dict, cols: list[dict]) -> dict | None:
    for col in cols:
        if col.get("self") is True or col.get("name") == entity.get("name"):
            return col
    return None


def _iter_history_items(entity: dict):
    for item in entity.get("history") or []:
        yield item
    for group in entity.get("sub_history") or []:
        for item in group.get("items") or []:
            yield item


def _self_comparison_cell_count(entity: dict) -> int:
    comparison = entity.get("comparison") or {}
    self_col = _find_self_col(entity, list(comparison.get("cols") or []))
    if not self_col:
        return 0
    cells = self_col.get("cells") or {}
    return len(cells) if isinstance(cells, dict) else 0
