"""サムネイル補完: events.jsonl の source_url から og:image を取得して thumb フィールドを追加。

source_url があり thumb がない行だけを対象に OGP を取得する。
JSON を再 dump して書き直す（AI-Pulse は表記揺れなし）。
collect_rss.py または run_daily.py から実行されるほか、単独でも使える。

使い方:
    python tools/backfill_thumb.py             # 全件補完
    python tools/backfill_thumb.py --dry-run   # 書き込まずプレビュー
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from fetch_ogp import fetch_ogp  # noqa: E402

DATA = ROOT / "data"
EVENTS = DATA / "events.jsonl"


def backfill(dry_run: bool = False) -> dict:
    """thumb がない全イベントに OGP 画像を補完する。"""
    events = []
    needs: list[int] = []

    for line in EVENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        ev = json.loads(line)
        events.append(ev)
        if ev.get("source_url") and "thumb" not in ev:
            needs.append(len(events) - 1)

    print(f"補完対象: {len(needs)} 件 / 全 {len(events)} 件", flush=True)
    if not needs:
        return {"ok": 0, "no_meta": 0, "error": 0}

    ok = no_meta = error = 0
    for idx in needs:
        ev = events[idx]
        url = ev["source_url"]
        try:
            result = fetch_ogp(url, timeout=10)
            thumb = result.get("og_image") or result.get("twitter_image")
            ev["thumb"] = thumb
            if thumb:
                ok += 1
                print(f"  OK   {ev['event_id']}: {thumb[:70]}", flush=True)
            else:
                no_meta += 1
                print(f"  --   {ev['event_id']}: {result['status']}", flush=True)
        except Exception as exc:
            ev["thumb"] = None
            error += 1
            print(f"  ERR  {ev['event_id']}: {exc}", file=sys.stderr, flush=True)
        time.sleep(0.5)

    if not dry_run:
        tmp = EVENTS.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        tmp.replace(EVENTS)
        print(f"書き込み完了: {len(events)} 行 (ok={ok} no_meta={no_meta} err={error})", flush=True)

    return {"ok": ok, "no_meta": no_meta, "error": error}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    dry_run = "--dry-run" in argv
    backfill(dry_run=dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
