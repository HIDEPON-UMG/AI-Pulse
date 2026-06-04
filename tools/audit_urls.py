#!/usr/bin/env python3
"""entities.jsonl / events.jsonl の全 URL を validate_urls の境界モジュールで一括検証する。

# 役割

- ad-hoc 監査: 開発者が手で走らせて死リンク棚卸し
- push ゲート: `--gate` モードで捏造混入時は exit 1 を返し、commit/push を物理的に止める
- 契約テスト: tests/test_urls_live.py からも同じ境界モジュール経由で呼ばれる

# CLI

```
./.venv/Scripts/python.exe tools/audit_urls.py                # 全 URL
./.venv/Scripts/python.exe tools/audit_urls.py --recent 7     # 直近 N 日 (event の date / entity の snapshot_date が直近)
./.venv/Scripts/python.exe tools/audit_urls.py --gate         # push gate モード (--recent 14 + 厳格 exit)
./.venv/Scripts/python.exe tools/audit_urls.py --max-workers 16
```

exit 0 = 全 URL 健全 / exit 1 = 1 件以上 fatal (= 捏造または恒久 404) / exit 2 = usage エラー。
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from tools.validate_urls import (  # noqa: E402
    extract_urls_from_entity,
    extract_urls_from_event,
    load_store,
    verify_urls,
)


def _parse_date(s: str) -> date | None:
    """YYYY-MM-DD を date に。失敗したら None。"""
    try:
        return datetime.strptime(str(s).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recent", type=int, default=0,
                    help="直近 N 日に絞る (0 = 全件)")
    ap.add_argument("--max-workers", type=int, default=8)
    ap.add_argument("--gate", action="store_true",
                    help="push gate モード (--recent 14 + 致命的フェイルで非ゼロ exit)")
    args = ap.parse_args()
    if args.gate and not args.recent:
        # entity の snapshot_date は更新頻度が低いので gate は 14 日に拡張 (event は date)
        args.recent = 14

    entities, events = load_store()
    if not entities and not events:
        print("entities.jsonl / events.jsonl が見つからない or 空", file=sys.stderr)
        return 2

    cutoff = date.today() - timedelta(days=args.recent) if args.recent else None

    refs = []
    if cutoff:
        # entity は snapshot_date、event は date を見て直近フィルタ
        for e in entities:
            d = _parse_date(e.get("snapshot_date", ""))
            if d and d >= cutoff:
                refs.extend(extract_urls_from_entity(e))
        for v in events:
            d = _parse_date(v.get("date", ""))
            if d and d >= cutoff:
                refs.extend(extract_urls_from_event(v))
    else:
        for e in entities:
            refs.extend(extract_urls_from_entity(e))
        for v in events:
            refs.extend(extract_urls_from_event(v))

    if not refs:
        scope = f"直近 {args.recent} 日" if cutoff else "全期間"
        print(f"対象 URL が 0 件 ({scope})")
        return 0

    scope = f"直近 {args.recent} 日" if cutoff else "全期間"
    print(f"対象 URL: {len(refs)} 件 ({scope}, workers={args.max_workers})")
    verdicts = verify_urls(refs, max_workers=args.max_workers)

    fatal = [v for v in verdicts if not v.ok]
    ok = len(verdicts) - len(fatal)
    print(f"\n結果: {ok}/{len(verdicts)} OK, {len(fatal)} NG")

    # ambiguous は通すが内訳を表示する (Bloomberg/theinformation 等は anti-bot)
    ambig = [v for v in verdicts if v.ok and ("ambiguous" in v.detail or "anti-bot" in v.detail)]
    if ambig:
        print(f"\n=== ambiguous OK (anti-bot 継続 or network unreachable) {len(ambig)} 件 ===")
        for v in ambig:
            print(f"  [{v.ref.location}] {v.detail}")
            print(f"    {v.ref.url}")

    if fatal:
        print("\n=== NG URL 一覧 (要差し替え) ===")
        for v in fatal:
            print(f"  [{v.ref.location}] {v.detail}")
            print(f"    {v.ref.url}")
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
