#!/usr/bin/env python3
"""既存 events.jsonl の「単語のみ rationale」を文章で再生成する汎用スクリプト。

なぜ重要か (意図):
  Part 7 で schema が rationale 各値 20 字以上を強制したため、既存 events.jsonl の
  「単語のみ rationale ("high"/"mid"/"low" 等)」を持つ event は schema 違反でロード
  不能になる。本スクリプトは llm_hybrid.regenerate_rationale を呼んで、各 event の
  headline + summary + summary_points + importance ラベルから rationale 3 軸を文章で
  再生成し、events.jsonl を上書きする。

  境界は llm_hybrid.regenerate_rationale に集約済み
  ([[feedback_check_design_principles]] §2)。本スクリプトは抽出ロジック
  (_needs_rationale_regen) と書き出しだけを持つ。

設計上の注意:
  - 既に「文章 rationale」を持つ event は触らない (再生成しない)
  - 各値が 20 字以上ある event はスキップ (= _RATIONALE_MIN_LEN を schema と揃える)
  - --dry-run は LLM を一切呼ばず件数とサンプルのみ表示
  - --limit N は先頭 N 件のみ再生成 (テスト・段階適用用)
  - 1 件失敗しても他は続行 (LLMError は warn ログ + 該当 entry はスキップ)
  - entity_context は None で渡す (Part 6 と同様 / entity_id スラグ混入事故防止)

使い方:
  ./.venv/Scripts/python.exe tools/regenerate_rationale.py --dry-run
  ./.venv/Scripts/python.exe tools/regenerate_rationale.py --limit 5
  ./.venv/Scripts/python.exe tools/regenerate_rationale.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "tools"))
import llm_hybrid  # noqa: E402  # regenerate_rationale (local_first / Gemini fallback)
import schema  # noqa: E402  # _RATIONALE_MIN_LEN を schema と揃える

EV_PATH = _ROOT / "data" / "events.jsonl"
_MIN_LEN = schema._RATIONALE_MIN_LEN  # 20 字以上を再生成不要とみなす


def _needs_rationale_regen(ev: dict) -> bool:
    """rationale が「文章として不十分」なら再生成対象 (True)。

    判定: rationale が dict でない / 3 キーが揃わない / どれか 1 つでも 20 字未満なら True。
    """
    r = ev.get("rationale")
    if not isinstance(r, dict):
        return True
    for k in ("importance", "impact", "buzz"):
        v = r.get(k)
        if not isinstance(v, str) or len(v) < _MIN_LEN:
            return True
    return False


def _scan_targets(events: list[dict]) -> list[tuple[int, dict]]:
    """events のうち再生成対象 (rationale が文章として不十分) を index 付きで返す。"""
    return [(idx, ev) for idx, ev in enumerate(events) if _needs_rationale_regen(ev)]


def _load_events(path: Path) -> list[dict]:
    return [
        json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]


def _dump_events(path: Path, events: list[dict]) -> None:
    out = [json.dumps(ev, ensure_ascii=False) for ev in events]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="LLM を呼ばず件数とサンプルのみ表示")
    parser.add_argument("--limit", type=int, default=None, help="先頭 N 件のみ再生成 (省略時は全件)")
    parser.add_argument("--data", type=Path, default=EV_PATH, help=f"events.jsonl のパス (既定: {EV_PATH})")
    args = parser.parse_args(argv)

    if not args.data.exists():
        print(f"events.jsonl が見つからない: {args.data}", file=sys.stderr)
        return 2

    events = _load_events(args.data)
    targets = _scan_targets(events)
    if args.limit is not None:
        targets = targets[: args.limit]

    print(f"events 全件: {len(events)}")
    print(f"再生成対象 (rationale 各値 < {_MIN_LEN} 字 or 欠落): {len(targets)} 件")

    if args.dry_run:
        print("\n--- dry-run: 先頭 10 件サンプル ---")
        for _, ev in targets[:10]:
            r = ev.get("rationale", {})
            lens = {k: len(r.get(k, "")) if isinstance(r.get(k), str) else 0
                    for k in ("importance", "impact", "buzz")}
            print(f"  [{ev.get('event_id')}] rationale 字数 {lens}")
        if len(targets) > 10:
            print(f"  ... 他 {len(targets) - 10} 件")
        print("\n(--dry-run のため events.jsonl は書き換えません)")
        return 0

    if not targets:
        print("再生成対象が 0 件のため終了します。")
        return 0

    success = 0
    failed: list[tuple[str, str]] = []
    t0 = time.monotonic()
    for n, (idx, ev) in enumerate(targets, 1):
        headline = ev.get("headline", "")
        summary = ev.get("summary", "")
        summary_points = ev.get("summary_points") or []
        importance_label = ev.get("importance", "mid")
        try:
            # entity_context は渡さない (Part 6 と同じ判断: entity_id スラグ混入事故防止)
            new_rationale = llm_hybrid.regenerate_rationale(
                headline,
                summary,
                summary_points,
                importance_label,
                entity_context=None,
            )
        except llm_hybrid.LLMError as exc:
            failed.append((ev.get("event_id", "?"), str(exc)))
            print(f"  [{n}/{len(targets)}] FAIL {ev.get('event_id')}: {exc}", file=sys.stderr)
            continue
        events[idx]["rationale"] = new_rationale
        success += 1
        elapsed = time.monotonic() - t0
        avg = elapsed / n
        eta = avg * (len(targets) - n)
        ilen = len(new_rationale.get("importance", ""))
        print(
            f"  [{n}/{len(targets)}] OK {ev.get('event_id')} "
            f"(importance {ilen}字 / avg {avg:.1f}s/件 / ETA {eta/60:.1f}min)"
        )

    _dump_events(args.data, events)
    print(f"\nRegenerated rationale for {success}/{len(targets)} events (失敗 {len(failed)} 件)")
    if failed:
        print("失敗 entry:", file=sys.stderr)
        for eid, msg in failed:
            print(f"  - {eid}: {msg}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
