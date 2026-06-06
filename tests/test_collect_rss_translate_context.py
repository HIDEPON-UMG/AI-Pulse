"""collect_rss.py の translate_headline_ja 呼出は entity_context=None で固定。

class of bugs (Part 6 で観測 / 2026-06-05):
  entity dict を entity_context として渡すと LLM プロンプトに
  「固有名詞ヒント: <name>, <vendor>」が注入され、headline に登場しない entity 名まで
  翻訳結果に強制混入する事故が出る。例:
    - 元 headline "Martin Scorsese Supports AI Company" に対し
      LLM が "AI 企業 **flux**" を注入 (entity_id=flux, name=FLUX のヒント由来)

恒久対策 ([[feedback_check_design_principles]] §2 境界 1 箇所集約 / §3 静的検査 1 ルール):
  apply_headline_ja / regenerate_rationale と契約を統一し、collect_rss も
  entity_context=None で呼ぶ。本テストはソース AST を直接検査し、
  「translate_headline_ja(...) 呼出の entity_context kwarg が必ず None リテラル」
  を locked-in する。collect_rss は外部依存 (fetch_article / Ollama / Gemini /
  Google News RSS) が大きくランタイムテストが重いため、静的検査でクラスを封じる。
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECT_RSS = ROOT / "tools" / "collect_rss.py"


def _translate_calls(source: str) -> list[ast.Call]:
    """ソース中の `*.translate_headline_ja(...)` 呼出ノードを全て返す。"""
    tree = ast.parse(source)
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "translate_headline_ja":
            calls.append(node)
    return calls


class TestCollectRssTranslateUsesNoneContext:
    def test_source_file_exists(self) -> None:
        assert COLLECT_RSS.is_file(), f"collect_rss.py が見つからない: {COLLECT_RSS}"

    def test_translate_headline_ja_is_called_at_least_once(self) -> None:
        source = COLLECT_RSS.read_text(encoding="utf-8")
        calls = _translate_calls(source)
        assert calls, (
            "collect_rss.py に translate_headline_ja(...) 呼出が無い。"
            "削除なら本テストごと撤去すること。"
        )

    def test_entity_context_is_always_none_literal(self) -> None:
        """全 translate_headline_ja 呼出で entity_context が None リテラルで明示される。

        - kwarg 指定なし → 失格 (将来の改修で entity を渡しても気付けない)
        - entity_context=entity / entity_context=some_dict → 失格 (捏造源)
        - entity_context=None → OK
        """
        source = COLLECT_RSS.read_text(encoding="utf-8")
        calls = _translate_calls(source)
        for call in calls:
            kws = {kw.arg: kw.value for kw in call.keywords if kw.arg}
            assert "entity_context" in kws, (
                f"line {call.lineno}: translate_headline_ja に entity_context kwarg が "
                "明示されていない。entity_context=None を明示すること "
                "([[feedback_check_design_principles]] §3)。"
            )
            value = kws["entity_context"]
            is_none = isinstance(value, ast.Constant) and value.value is None
            assert is_none, (
                f"line {call.lineno}: translate_headline_ja の entity_context は "
                f"None リテラル固定。実際: {ast.unparse(value)!r}"
            )
