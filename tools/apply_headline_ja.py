#!/usr/bin/env python3
"""既存 events.jsonl の英語タイトルに headline_ja を遡及付与する汎用スクリプト。

なぜ重要か (意図):
  collect_rss.py は新規採用 entry にのみ headline_ja を自動付与する設計 (handoff Part 5)。
  既に events.jsonl に存在する英語見出し (= ASCII 比率 0.95+ で headline_ja 未付与) を
  一括で日本語化したいときの遡及ツール。Part 4 で Claude 直接翻訳した一回限り版
  (apply_headline_ja_2026_06_05.py) の構造を、llm_hybrid 経由・全件スキャン型に
  汎用化した後継 (handoff Part 5 「スコープ B」の本実装)。

  境界は llm_hybrid.translate_headline_ja に集約済み
  ([[feedback_check_design_principles]] §2 「境界 1 箇所集約」)。本スクリプトは判定
  ロジック (_needs_headline_ja) も collect_rss から再利用し、二重定義を作らない。

設計上の注意:
  - 既に headline_ja を持つ entry は触らない (再翻訳しない)
  - 非 ASCII 混在見出し (日本語混在) は触らない (_needs_headline_ja=False)
  - --dry-run は LLM を一切呼ばず件数とサンプルのみ表示 (events.jsonl は書き換えない)
  - --limit N は先頭 N 件のみ翻訳 (テスト・段階適用用)
  - 1 件失敗しても他は続行 (LLMError は warn ログ + 該当 entry はスキップ)
  - entity_context は None で渡す (= ヒントなし)
    (2026-06-05 検証で entity_id を entity_name として渡すと、LLM が entity_id スラグを
     「公式な固有名詞表記」と誤解して翻訳結果に挿入・改変する事故を観測したため
     [例: 元 headline に無い "AI 企業 flux" の挿入、"Physical Intelligence" の
     ハイフン連結化]。元 headline 本文だけを根拠に翻訳させる安全側に倒した)

使い方:
  ./.venv/Scripts/python.exe tools/apply_headline_ja.py --dry-run
  ./.venv/Scripts/python.exe tools/apply_headline_ja.py --limit 5
  ./.venv/Scripts/python.exe tools/apply_headline_ja.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "tools"))
import collect_rss  # noqa: E402  # _needs_headline_ja / _ascii_ratio を再利用
import llm_hybrid  # noqa: E402  # translate_headline_ja (local_first / Gemini fallback)

EV_PATH = _ROOT / "data" / "events.jsonl"


def _scan_targets(events: list[dict]) -> list[tuple[int, dict]]:
    """events のうち翻訳対象 (英語 ASCII>=0.95 かつ headline_ja 未付与) を index 付きで返す。"""
    targets: list[tuple[int, dict]] = []
    for idx, ev in enumerate(events):
        if ev.get("headline_ja"):
            continue
        headline = ev.get("headline", "")
        if collect_rss._needs_headline_ja(headline):
            targets.append((idx, ev))
    return targets


def _load_events(path: Path) -> list[dict]:
    events: list[dict] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        events.append(json.loads(ln))
    return events


def _dump_events(path: Path, events: list[dict]) -> None:
    """events を jsonl 形式で書き出す (apply_headline_ja_2026_06_05.py と同じ単純 write)。"""
    out = [json.dumps(ev, ensure_ascii=False) for ev in events]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="LLM を呼ばず件数とサンプルのみ表示")
    parser.add_argument("--limit", type=int, default=None, help="先頭 N 件のみ翻訳 (省略時は全件)")
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
    print(f"翻訳対象 (ASCII>=0.95 かつ headline_ja 未付与): {len(targets)} 件")

    if args.dry_run:
        print("\n--- dry-run: 先頭 10 件サンプル ---")
        for _, ev in targets[:10]:
            print(f"  [{ev.get('event_id')}] {ev.get('headline')}")
        if len(targets) > 10:
            print(f"  ... 他 {len(targets) - 10} 件")
        print("\n(--dry-run のため events.jsonl は書き換えません)")
        return 0

    if not targets:
        print("翻訳対象が 0 件のため終了します。")
        return 0

    success = 0
    failed: list[tuple[str, str]] = []
    t0 = time.monotonic()
    for n, (idx, ev) in enumerate(targets, 1):
        headline = ev.get("headline", "")
        try:
            # entity_context は渡さない (entity_id のスラグが翻訳結果に挿入される事故を防ぐ)
            ja = llm_hybrid.translate_headline_ja(headline, entity_context=None)
        except llm_hybrid.LLMError as exc:
            failed.append((ev.get("event_id", "?"), str(exc)))
            print(f"  [{n}/{len(targets)}] FAIL {ev.get('event_id')}: {exc}", file=sys.stderr)
            continue
        events[idx]["headline_ja"] = ja
        success += 1
        elapsed = time.monotonic() - t0
        avg = elapsed / n
        eta = avg * (len(targets) - n)
        print(f"  [{n}/{len(targets)}] OK {ev.get('event_id')} -> {ja} (avg {avg:.1f}s/件, ETA {eta/60:.1f}min)")

    _dump_events(args.data, events)
    print(f"\nApplied headline_ja to {success}/{len(targets)} events (失敗 {len(failed)} 件)")
    if failed:
        print("失敗 entry:", file=sys.stderr)
        for eid, msg in failed:
            print(f"  - {eid}: {msg}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
