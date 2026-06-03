"""既存 RSS イベントの domain-only source_url を Google News リダイレクト URL で上書きする。

対象: source_url にパスコンポーネントが無いイベント（例: https://www.bloomberg.com）
手順:
  1. 各 entity の RSS を再取得（collect_rss._fetch_rss を流用）
  2. 正規化ヘッドラインで既存イベントとマッチング
  3. マッチしたイベントの source_url を item["link"] に更新
  4. events.jsonl を上書き保存

実行:
  python tools/backfill_source_url.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import collect_rss  # noqa: E402
import schema  # noqa: E402

DATA = ROOT / "data"


def _domain_only(url: str) -> bool:
    """URL にパスが無い（出版社ドメインのみ）かどうかを返す。"""
    p = urlparse(url or "")
    return not p.path.strip("/")


def _normalize(title: str) -> str:
    """ヘッドラインを比較用に正規化（小文字・記号除去）。"""
    return re.sub(r"[^a-z0-9\s]", "", title.lower()).strip()


def backfill() -> dict:
    entities, events = schema.validate_store(
        DATA / "entities.jsonl", DATA / "events.jsonl"
    )

    # entity_id ごとに domain-only URL イベントを収集
    needs_fix: dict[str, list[dict]] = {}
    for ev in events:
        if "rss" in ev.get("event_id", "") and _domain_only(ev.get("source_url", "")):
            needs_fix.setdefault(ev["entity_id"], []).append(ev)

    total_fixed = 0
    eid_map = {e["entity_id"]: e for e in entities}

    for entity_id, ev_list in needs_fix.items():
        entity = eid_map.get(entity_id)
        if not entity:
            continue

        query = collect_rss.build_query(entity)
        print(f"  [{entity_id}] query={query!r}  ({len(ev_list)} events to fix)")
        items = collect_rss._fetch_rss(query, num=10)
        time.sleep(0.5)

        # 正規化ヘッドライン → item["link"] のマップを作成
        link_map: dict[str, str] = {}
        for item in items:
            key = _normalize(item["title"])
            link_map[key] = item["link"]

        for ev in ev_list:
            key = _normalize(ev["headline"])
            if key in link_map:
                ev["source_url"] = link_map[key]
                total_fixed += 1
                print(f"    [OK] {ev['event_id']}: {link_map[key][:70]}")
            else:
                print(f"    [--] {ev['event_id']}: マッチなし")

    # events.jsonl を上書き
    out_path = DATA / "events.jsonl"
    ev_by_id = {ev["event_id"]: ev for ev in events}
    with open(out_path, "w", encoding="utf-8") as f:
        for ev in ev_by_id.values():
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    total_needs = sum(len(v) for v in needs_fix.values())
    print(f"\nバックフィル完了: {total_fixed} 件を更新 / {total_needs} 件対象")
    return {"fixed": total_fixed, "total": total_needs}


if __name__ == "__main__":
    backfill()
