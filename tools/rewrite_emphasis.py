"""既存 events.jsonl の summary / summary_points に対し、強調記法 3 種を意味分けに沿って振り直す。

**Why（意図）**: Gemini プロンプトには 3 種記法（**太字** / ==マーカー== / __下線__）を意味分けして
使うよう書いたが、既存 107 件は古いプロンプト時代のデータで **太字** に偏っている（実測:
**=559 / ===44 / __=22）。
Sonnet（=このスクリプト）で API コストを使わず決定論的に振り分け直すことで、CSS の 3 種視覚レイヤー
(下半マーカー / 波線下線 / 太字) を初日から活かす。

**振り分けルール**（優先度: 数値 > 動作 > 太字維持）:
- 既存の `==X==` と `__X__` は touched しない（LLM が意図的に付けた可能性を尊重）。
- `**X**` のうち X 内に **数値表現**（金額・パーセント・倍率・規模）を含む → `==X==`（結論・決定打）。
- `**X**` のうち X 内に **動詞性語**（発表・公開・採用・買収など）を含む → `__X__`（動作・出来事）。
- それ以外（人名・組織名・サービス名・技術用語など固有名）→ `**X**` 維持。

**冪等性**: スクリプトを 2 回走らせても結果が変わらない（既存 ==/__ は触らない・置換後の == / __ は対象外）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVENTS_PATH = ROOT / "data" / "events.jsonl"

# 数値表現パターン（マーカー候補）。金額・パーセント・倍率・規模・大きな整数を捕捉する。
# 「3 倍」「10%」「$7B」「7 億ドル」「23 万件」「89% Devin 上回り」などをカバー。
_NUM_RE = re.compile(
    r"(?:"
    r"\d+(?:\.\d+)?\s*[%％倍]"               # 12% / 3.5倍
    r"|[\$¥€]\s*\d+(?:\.\d+)?\s*[BMK]?"     # $7B / ¥1.2M
    r"|\d+(?:\.\d+)?\s*(?:億|兆|万|千)"      # 7億 / 1.2兆 / 23万
    r"|\d+(?:\.\d+)?\s*(?:ドル|円|EUR|GBP|USD|元)"  # 70 ドル / 100 円
    r"|\d{2,}(?:,\d{3})+"                    # 1,000,000 / 23,456
    r"|\d{4,}"                                # 4 桁以上の生数値（年号は除外したいが過剰検出は許容）
    r")"
)

# 動詞性語（下線候補）。「動き」「アクション」「出来事」を示す日本語動詞・名詞句。
_VERB_TERMS = (
    "発表", "公開", "提供開始", "ローンチ", "リリース", "解禁", "始動", "開始",
    "廃止", "終了", "停止", "撤退", "終焉",
    "採用", "買収", "統合", "提携", "締結", "合意", "投資", "出資", "調達", "資金調達",
    "導入", "配信", "実装", "搭載", "リブランド",
    "達成", "突破", "上回り", "上回る", "獲得", "受賞",
    "完了", "完成", "確立",
    "切替", "切り替え", "移行",
    "正式版", "本リリース",
)


def _has_number(text: str) -> bool:
    return bool(_NUM_RE.search(text))


def _has_verb(text: str) -> bool:
    return any(v in text for v in _VERB_TERMS)


# `**X**` だけを対象に置換。`==X==` と `__X__` はマッチさせない（[^*] で守る）。
_BOLD_RE = re.compile(r"\*\*([^*\n]+?)\*\*")


def _transform_inline(s: str) -> str:
    """文字列内の `**X**` を内容に応じて `==X==` / `__X__` / `**X**` のいずれかに振り分ける。

    既存の `==X==` / `__X__` は変換対象外（regex が `**...**` 限定で守る）。
    """
    def _repl(m: re.Match[str]) -> str:
        inner = m.group(1).strip()
        if not inner:
            return m.group(0)
        # 優先度: 数値 > 動作 > 太字維持
        if _has_number(inner):
            return f"=={inner}=="
        if _has_verb(inner):
            return f"__{inner}__"
        return f"**{inner}**"

    return _BOLD_RE.sub(_repl, s)


def rewrite_event(ev: dict) -> tuple[dict, bool]:
    """1 event の summary / summary_points を変換し、変更があれば (新, True) を返す。"""
    before_sum = ev.get("summary") or ""
    after_sum = _transform_inline(before_sum)
    before_pts = list(ev.get("summary_points") or [])
    after_pts = [_transform_inline(p) for p in before_pts]
    changed = (after_sum != before_sum) or (after_pts != before_pts)
    if changed:
        new = dict(ev)
        new["summary"] = after_sum
        new["summary_points"] = after_pts
        return new, True
    return ev, False


def main() -> None:
    lines = EVENTS_PATH.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    n_changed = 0
    n_total = 0
    counters = {"mark_added": 0, "und_added": 0, "bold_kept": 0}
    for line in lines:
        if not line.strip():
            continue
        n_total += 1
        ev = json.loads(line)
        new_ev, changed = rewrite_event(ev)
        if changed:
            n_changed += 1
            counters["mark_added"] += new_ev["summary"].count("==") // 2 - ev.get("summary", "").count("==") // 2
            counters["und_added"] += new_ev["summary"].count("__") // 2 - ev.get("summary", "").count("__") // 2
        out.append(json.dumps(new_ev, ensure_ascii=False))
    EVENTS_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"[rewrite_emphasis] {n_changed}/{n_total} events 変更（summary のみカウント: "
          f"==追加={counters['mark_added']} / __追加={counters['und_added']}）")


if __name__ == "__main__":
    main()
