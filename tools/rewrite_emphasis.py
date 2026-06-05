"""events.jsonl の summary / summary_points に強調記法 3 種を意味分けで付与・振り直す。

**Why（意図）**: 強調記法（**太字** / ==マーカー== / __下線__）の意味分け責務を LLM プロンプトから
コード側に物理移管する。CSS の 3 種視覚レイヤー（下半マーカー / 波線下線 / 太字）を初日から活かす。

**2 つのモード**:
- `rewrite_event` (レガシー振り分け): 既存 `**X**` を意味で `==X==` / `__X__` に振り直す。
  旧 prompt 時代の entry（**太字** 偏重）を後段で 3 種化する用途。
- `add_emphasis_event` (新規プレーンテキスト付与): プレーンテキストから数値/動詞/固有名を検出して
  `==X==` / `__X__` / `**X**` を新規付与する。新 prompt `extract_grounded.md` の plain text 出力に対応。

**振り分けルール**（優先度: 数値 > 動作 > 固有名）:
- `**X**` のうち X 内に **数値表現**（金額・パーセント・倍率・規模）を含む → `==X==`（結論・決定打）。
- `**X**` のうち X 内に **動詞性語**（発表・公開・採用・買収など）を含む → `__X__`（動作・出来事）。
- それ以外（人名・組織名・サービス名・技術用語など固有名）→ `**X**` 維持。
- `add_emphasis_event` モードでは entity_context から固有名候補（entity name / vendor / competitors）
  を抽出し、本文に出現する場合のみ `**X**` を付与する（汎用 NER は持たない）。

**冪等性**: いずれのモードも 2 回適用で結果不変。既存 `==X==` / `__X__` / `**X**` の内側は touched しない。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVENTS_PATH = ROOT / "data" / "events.jsonl"
ENTITIES_PATH = ROOT / "data" / "entities.jsonl"

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


# 既存記法のカバー範囲検出用（`==X==` / `__X__` / `**X**` をまとめて捕捉）
_EXISTING_MARKUP_RE = re.compile(
    r"==[^=\n]+?==|__[^_\n]+?__|\*\*[^*\n]+?\*\*"
)


def _collect_covered_spans(text: str) -> list[tuple[int, int]]:
    """既存の `==X==` / `__X__` / `**X**` 範囲を (start, end) リストで返す。"""
    return [(m.start(), m.end()) for m in _EXISTING_MARKUP_RE.finditer(text)]


def _is_covered(start: int, end: int, covered: list[tuple[int, int]]) -> bool:
    """[start, end) が既存記法のいずれかに完全に含まれていれば True。"""
    return any(s <= start and end <= e for s, e in covered)


def _extract_proper_nouns(entity_context: dict | None) -> list[str]:
    """entity_context（entity dict）から固有名候補リストを抽出する。

    汎用 NER は持たないため、entity の name / vendor / competitors[].name / relations[].name
    と、ドメイン上の主要オファリング名（offering）に限定する。長い文字列を先に置くことで
    部分一致による誤マッチを避ける（例: "Claude Opus 4.8" を "Claude" より先に処理）。
    """
    if not entity_context:
        return []
    candidates: list[str] = []
    for key in ("name", "vendor", "offering"):
        v = entity_context.get(key)
        if isinstance(v, str) and v.strip():
            candidates.append(v.strip())
    for k in ("competitors", "relations"):
        for item in entity_context.get(k) or []:
            if isinstance(item, dict):
                v = item.get("name")
                if isinstance(v, str) and v.strip():
                    candidates.append(v.strip())
            elif isinstance(item, str) and item.strip():
                candidates.append(item.strip())
    # 重複削除しつつ長い順（長一致優先）にソート
    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    unique.sort(key=len, reverse=True)
    return unique


def _add_inline_emphasis(text: str, *, proper_nouns: list[str] | None = None) -> str:
    """プレーンテキストから数値/動詞/固有名を検出して `==X==` / `__X__` / `**X**` を付与する。

    冪等: 既存の `==X==` / `__X__` / `**X**` 範囲は touched しない。
    優先度: 数値 > 動作 > 固有名（重複範囲は先に来たものを採用）。

    Args:
        text: 強調記法を付与したいプレーン（or 一部マーク済）テキスト。
        proper_nouns: 固有名として `**X**` で囲む候補。entity_context から抽出した name/vendor 等。

    Returns:
        強調記法付与済の新テキスト。入力に既存マーク済範囲があれば保持。
    """
    if not text:
        return text
    covered = _collect_covered_spans(text)

    candidates: list[tuple[int, int, str]] = []

    # 1. 数値表現 → `==X==`
    for m in _NUM_RE.finditer(text):
        if not _is_covered(m.start(), m.end(), covered):
            candidates.append((m.start(), m.end(), f"=={m.group(0)}=="))

    # 2. 動詞性語 → `__X__`
    for verb in _VERB_TERMS:
        for m in re.finditer(re.escape(verb), text):
            if not _is_covered(m.start(), m.end(), covered):
                candidates.append((m.start(), m.end(), f"__{m.group(0)}__"))

    # 3. 固有名 → `**X**`（長一致優先で proper_nouns はソート済）
    for noun in proper_nouns or []:
        if not noun:
            continue
        for m in re.finditer(re.escape(noun), text):
            if not _is_covered(m.start(), m.end(), covered):
                candidates.append((m.start(), m.end(), f"**{m.group(0)}**"))

    # 非重複に絞る（位置順 + 先勝ち）
    candidates.sort(key=lambda c: (c[0], c[1]))
    chosen: list[tuple[int, int, str]] = []
    last_end = 0
    for start, end, repl in candidates:
        if start >= last_end:
            chosen.append((start, end, repl))
            last_end = end

    # 後ろから前へ置換適用（前から適用するとオフセットがずれる）
    result_parts: list[str] = []
    cursor = 0
    for start, end, repl in chosen:
        result_parts.append(text[cursor:start])
        result_parts.append(repl)
        cursor = end
    result_parts.append(text[cursor:])
    return "".join(result_parts)


def add_emphasis_event(
    ev: dict, *, entity_context: dict | None = None
) -> tuple[dict, bool]:
    """1 event の summary / summary_points にプレーンテキスト用の強調記法を付与する。

    `rewrite_event` との違い:
    - `rewrite_event` は既存 `**X**` を意味で振り分けるレガシーモード。
    - `add_emphasis_event` はプレーンテキストから数値/動詞/固有名を検出して 3 種記法を新規付与する。

    既存記法がある entry は冪等に処理（再付与しない）。
    """
    proper_nouns = _extract_proper_nouns(entity_context)
    before_sum = ev.get("summary") or ""
    after_sum = _add_inline_emphasis(before_sum, proper_nouns=proper_nouns)
    before_pts = list(ev.get("summary_points") or [])
    after_pts = [_add_inline_emphasis(p, proper_nouns=proper_nouns) for p in before_pts]
    changed = (after_sum != before_sum) or (after_pts != before_pts)
    if changed:
        new = dict(ev)
        new["summary"] = after_sum
        new["summary_points"] = after_pts
        return new, True
    return ev, False


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
    """events.jsonl 全件に rewrite_event + add_emphasis_event を順次適用してデータを整合させる。

    冪等: 既存の `==X==` / `__X__` / `**X**` は touched しない。
    旧 prompt 由来の `**X**` 偏重 entry → rewrite_event で意味分け → 追加で add_emphasis_event を
    通して数値・動詞・固有名 (entity_context 由来) を補完する。
    新 prompt 由来の plain text entry → rewrite_event は no-op → add_emphasis_event で 3 種付与。
    """
    entities = {}
    if ENTITIES_PATH.exists():
        for line in ENTITIES_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                entities[e.get("entity_id")] = e
    lines = EVENTS_PATH.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    n_rewritten = 0
    n_added = 0
    n_total = 0
    counters = {"mark_added": 0, "und_added": 0, "bold_added": 0}
    for line in lines:
        if not line.strip():
            continue
        n_total += 1
        ev = json.loads(line)
        # 1) 旧 `**X**` を意味で振り分け（レガシー対応・冪等）
        ev_step1, rewritten = rewrite_event(ev)
        if rewritten:
            n_rewritten += 1
        # 2) プレーン部分から数値/動詞/固有名を検出して 3 種付与
        ctx = entities.get(ev_step1.get("entity_id"))
        ev_step2, added = add_emphasis_event(ev_step1, entity_context=ctx)
        if added:
            n_added += 1
            counters["mark_added"] += ev_step2["summary"].count("==") // 2 - ev_step1["summary"].count("==") // 2
            counters["und_added"] += ev_step2["summary"].count("__") // 2 - ev_step1["summary"].count("__") // 2
            counters["bold_added"] += ev_step2["summary"].count("**") // 2 - ev_step1["summary"].count("**") // 2
        out.append(json.dumps(ev_step2, ensure_ascii=False))
    EVENTS_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(
        f"[rewrite_emphasis] {n_rewritten}/{n_total} events rewrite + {n_added}/{n_total} add_emphasis "
        f"(summary 集計: ==追加={counters['mark_added']} / __追加={counters['und_added']} / "
        f"**追加={counters['bold_added']})"
    )


if __name__ == "__main__":
    main()
