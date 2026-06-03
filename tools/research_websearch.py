"""速報ジョブ（短周期）: WebSearch で集めた候補を L2 デルタとして取り込む。

WebSearch 自体は LLM（claude -p セッション）が prompts/breaking_websearch.md に従って実行し、
候補を L2 デルタ schema の JSON 配列として本モジュールに渡す。本モジュールは決定論パートだけを担う:
検証 → 掲載閾値 → 重複排除 → カルテ更新フック → 永続化（= store.ingest_events）。
（収集/下書きは LLM、ルーティング/閾値/重複/変換はコード、の分担。）

使い方:
    python research_websearch.py candidates.json
    candidates.json は L2 デルタ schema の配列（claude -p が出力したもの）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import store  # noqa: E402

DATA = ROOT / "data"


def ingest_breaking(candidates, entities_path=None, events_path=None) -> dict:
    """速報候補（L2 デルタ dict のリスト）を取り込み、結果サマリを返す。"""
    return store.ingest_events(
        entities_path or DATA / "entities.jsonl",
        events_path or DATA / "events.jsonl",
        candidates,
    )


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python research_websearch.py <candidates.json>", file=sys.stderr)
        return 2
    candidates = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    r = ingest_breaking(candidates)
    print(
        f"取り込み完了: 採用 {len(r['added'])} 件 / "
        f"重複スキップ {r['skipped_dup']} 件 / 閾値スキップ {r['skipped_score']} 件"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
