"""採用済み event の軽量品質監査。

目的:
  本線のローカル LLM 抽出は維持したまま、採用 event だけを Flash-Lite で監査し、
  誤訳・誇張表現・用語辞書候補を JSONL に残す。監査は観測レイヤーなので、失敗しても
  日次バッチや掲載を止めない。
"""
from __future__ import annotations

import copy
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import config  # noqa: E402
import llm_gemini  # noqa: E402

LOG_DIR = ROOT / "_logs"

AuditFn = Callable[[str, dict], dict]


def build_audit_record(event: dict, article_text: str) -> dict:
    """監査に必要な event snapshot と本文をまとめる。

    event は後続処理で変更される可能性があるため deep copy し、ログやテストが参照する
    監査時点の内容を固定する。
    """
    return {
        "event": copy.deepcopy(event),
        "article_text": (article_text or "")[: config.QUALITY_AUDIT_MAX_BODY_CHARS],
    }


def _date_key(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y%m%d")


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _term_candidates(event: dict, result: dict) -> list[dict]:
    rows: list[dict] = []
    for candidate in result.get("term_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        rows.append({
            "event_id": event.get("event_id"),
            "entity_id": event.get("entity_id"),
            "source_url": event.get("source_url"),
            "candidate": candidate,
        })
    return rows


def audit_records(
    records: list[dict],
    *,
    audit_fn: AuditFn = llm_gemini.audit_event_quality,
    log_dir: Path = LOG_DIR,
    now: datetime | None = None,
) -> dict:
    """採用 event の監査を実行し、結果と辞書候補を JSONL に追記する。

    Returns:
        {"audited": int, "ok": int, "warn": int, "fail": int, "errors": int,
         "term_candidates": int, "log_path": str | None, "candidate_path": str | None}
    """
    stats = {
        "audited": 0,
        "ok": 0,
        "warn": 0,
        "fail": 0,
        "errors": 0,
        "term_candidates": 0,
        "log_path": None,
        "candidate_path": None,
    }
    if not records or not config.QUALITY_AUDIT_ENABLED:
        return stats

    date_key = _date_key(now)
    log_path = log_dir / f"quality_audit_{date_key}.jsonl"
    candidate_path = log_dir / f"editorial_terms_candidates_{date_key}.jsonl"
    log_rows: list[dict] = []
    candidate_rows: list[dict] = []

    for record in records:
        event = record.get("event") or {}
        article_text = record.get("article_text") or ""
        stats["audited"] += 1
        try:
            result = audit_fn(article_text, event)
            status = str(result.get("status") or "warn").lower()
            if status not in {"ok", "warn", "fail"}:
                status = "warn"
            stats[status] += 1
            row = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "model": config.QUALITY_AUDIT_MODEL,
                "event_id": event.get("event_id"),
                "entity_id": event.get("entity_id"),
                "status": status,
                "issues": result.get("issues") or [],
                "notes": result.get("notes") or "",
            }
            log_rows.append(row)
            new_candidates = _term_candidates(event, result)
            candidate_rows.extend(new_candidates)
            stats["term_candidates"] += len(new_candidates)
        except Exception as exc:
            stats["errors"] += 1
            log_rows.append({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "model": config.QUALITY_AUDIT_MODEL,
                "event_id": event.get("event_id"),
                "entity_id": event.get("entity_id"),
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })

    _append_jsonl(log_path, log_rows)
    _append_jsonl(candidate_path, candidate_rows)
    stats["log_path"] = str(log_path)
    stats["candidate_path"] = str(candidate_path) if candidate_rows else None
    return stats
