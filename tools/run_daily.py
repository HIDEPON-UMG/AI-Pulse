"""日次バッチ: L2 RSS 収集 + 当日追加エンティティのカルテ fast 更新 + サイト再生成

Task Scheduler から scripts/run_daily.bat 経由で毎日 7:00 に実行。
claude -p / SDK 不使用。NotebookLM CLI（fast モード）を直接呼び出す。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import backfill_thumb  # noqa: E402
import collect_rss  # noqa: E402
import generate_pages  # noqa: E402
import research_notebooklm as nb  # noqa: E402
import schema  # noqa: E402

DATA = ROOT / "data"


def _fast_update(entity: dict) -> None:
    """1 エンティティを fast モードで NotebookLM 収集 → carte_fields → apply_deepdive。"""
    eid = entity["entity_id"]
    query = collect_rss.build_query(entity)
    print(f"  カルテ更新 [{eid}] query={query!r}")
    # Cookie を温める
    nb._nb(["auth", "refresh"], timeout=30)
    # ノートブック作成（fast: 通常 1〜3 分）
    cp = nb._nb(["create", f"AI-Pulse daily {eid}"])
    nb_id = nb._parse_notebook_id(cp.stdout)
    nb._nb([
        "source", "add-research", query,
        "--mode", "fast", "--import-all", "--timeout", "300",
        "-n", nb_id,
    ])
    # axis ごと ask → carte_fields → 永続化
    fields = nb.build_carte_fields(entity, nb_id)
    nb.apply_deepdive(eid, fields)
    print(f"    完了: {eid}")


def run_daily() -> None:
    print("=== AI-Pulse 日次バッチ 開始 ===")

    # Step 1: RSS 収集（L2 events）
    print("\n--- Step 1: RSS 収集 ---")
    result = collect_rss.collect_entities()
    added_events = result["added"]

    # Step 2: 当日更新エンティティのカルテ fast 更新
    if not added_events:
        print("新着なし。カルテ更新をスキップします。")
    else:
        updated_eids = list({ev["entity_id"] for ev in added_events})
        print(f"\n--- Step 2: カルテ fast 更新 ({len(updated_eids)} 件) ---")
        entities, _ = schema.validate_store(DATA / "entities.jsonl", DATA / "events.jsonl")
        by_id = {e["entity_id"]: e for e in entities}
        for eid in updated_eids:
            entity = by_id.get(eid)
            if entity is None:
                continue
            try:
                _fast_update(entity)
            except Exception as exc:
                print(f"    カルテ更新失敗 ({eid}): {exc}", file=sys.stderr)
            time.sleep(3)

    # Step 3: サムネイル補完
    print("\n--- Step 3: サムネイル補完 ---")
    backfill_thumb.backfill()

    # Step 4: サイト再生成
    print("\n--- Step 4: サイト再生成 ---")
    generate_pages.main()
    print("=== 日次バッチ 完了 ===")


if __name__ == "__main__":
    run_daily()
