"""週次バッチ: 全エンティティの Ollama カルテ更新（L1）+ サイト再生成

Task Scheduler から scripts/run_weekly.ps1 経由で月曜 7:00 に実行。
claude -p / SDK / NotebookLM 不使用。採用済み event と既存 entity を根拠に Ollama で更新する。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import collect_rss  # noqa: E402
import generate_pages  # noqa: E402
import research_ollama as carte  # noqa: E402
import schema  # noqa: E402

DATA = ROOT / "data"


def _deep_update(entity: dict, events: list[dict]) -> None:
    """1 エンティティを Ollama で更新する。"""
    eid = entity["entity_id"]
    query = collect_rss.build_query(entity)
    print(f"  [{eid}] backend=ollama query={query!r}")
    carte.update_entity(entity, events)
    print(f"    完了: {eid}")


def run_weekly() -> None:
    print("=== AI-Pulse 週次バッチ 開始 ===")
    entities, events = schema.validate_store(DATA / "entities.jsonl", DATA / "events.jsonl")
    update_failures: list[str] = []

    for entity in entities:
        try:
            entity_events = [ev for ev in events if ev["entity_id"] == entity["entity_id"]]
            _deep_update(entity, entity_events)
        except Exception as exc:
            print(f"  失敗 ({entity['entity_id']}): {exc}", file=sys.stderr)
            update_failures.append(entity["entity_id"])
        time.sleep(5)

    print("\n--- サイト再生成 ---")
    generate_pages.main()
    if update_failures:
        raise RuntimeError(f"週次カルテ更新失敗: {len(update_failures)} 件 ({', '.join(update_failures)})")
    print("=== 週次バッチ 完了 ===")


if __name__ == "__main__":
    run_weekly()
