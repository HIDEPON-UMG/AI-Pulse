"""週次バッチ: 全エンティティのカルテ deep 更新（L1）+ サイト再生成

Task Scheduler から scripts/run_weekly.ps1 経由で月曜 7:00 に実行。
claude -p / SDK 不使用。NotebookLM CLI（deep モード）を直接呼び出す。
deep は非同期（kick_deep）→ ポーリング（collect）の 2 段で処理する。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import collect_rss  # noqa: E402
import config  # noqa: E402
import generate_pages  # noqa: E402
import research_notebooklm as nb  # noqa: E402
import schema  # noqa: E402

DATA = ROOT / "data"
_POLL_INTERVAL = config.DEEP_POLL_MINUTES * 60   # 秒換算
_POLL_MAX = int(40 * 60 / _POLL_INTERVAL)         # 最大 40 分待つ


def _deep_update(entity: dict) -> None:
    """1 エンティティを deep モードで更新する（kick → ポーリング → build_carte_fields → apply）。"""
    eid = entity["entity_id"]
    query = collect_rss.build_query(entity)
    print(f"  [{eid}] query={query!r}")

    nb._nb(["auth", "refresh"], timeout=30)
    cp = nb._nb(["create", f"AI-Pulse weekly {eid}"])
    nb_id = nb._parse_notebook_id(cp.stdout)

    # 段A: deep research を非同期キック
    nb.kick_deep(eid, query, notebook_id=nb_id)

    # 段B: ready になるまでポーリング（最大 40 分）
    dummy_questions = [f"Summarize {entity.get('name', eid)} briefly."]
    for attempt in range(_POLL_MAX):
        time.sleep(_POLL_INTERVAL)
        r = nb.collect(eid, dummy_questions)
        if r.get("ready"):
            break
        print(f"    ({attempt + 1}/{_POLL_MAX}) まだ処理中...")
    else:
        raise TimeoutError(f"deep research タイムアウト: {eid}")

    # axis ごと ask → carte_fields → 永続化
    fields = nb.build_carte_fields(entity, nb_id)
    nb.apply_deepdive(eid, fields)
    print(f"    完了: {eid}")


def run_weekly() -> None:
    print("=== AI-Pulse 週次バッチ 開始 ===")
    entities, _ = schema.validate_store(DATA / "entities.jsonl", DATA / "events.jsonl")
    update_failures: list[str] = []

    for entity in entities:
        try:
            _deep_update(entity)
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
