"""契約テスト: rewrite_emphasis.rewrite_event の振り分けロジック。

なぜ重要か（意図）:
  2026-06-05 (追補11) で強調記法 (** / == / __) の意味分け責務を LLM プロンプトから
  rewrite_emphasis 側に物理的に移管した。LLM はプレーンテキストで要約を返し、強調は
  決定論コードで振り分ける構成。class of bug を 3 件で固定する:
    1. 数値表現 (金額・%・倍率) を含む **太字** は ==マーカー== に置換される（決定打）
    2. 動詞性語 (発表・公開・買収など) を含む **太字** は __下線__ に置換される（動作）
    3. 既存の ==X== / __X__ は touched しない（冪等性）

  これは旧 tests/test_llm_gemini.py::test_emphasis_only_bold_retries_once /
  test_emphasis_no_marks_at_all_fails の責務移管先（[[feedback_check_design_principles]] §2）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import rewrite_emphasis  # noqa: E402


class TestRewriteEmphasisInline(unittest.TestCase):
    def test_bold_with_number_is_promoted_to_mark(self):
        """**89%** や **$15/Mtok** など数値表現を含む太字は ==マーカー== に昇格。

        旧 LLM プロンプト「==マーカー== は決定打となる数値・結論」を rewrite_emphasis に物理化。
        """
        s = "**Anthropic** が **89% Devin 上回り** を達成"
        out = rewrite_emphasis._transform_inline(s)
        self.assertIn("==89% Devin 上回り==", out, "数値含む太字は ==マーカー== に変換されるべき")
        self.assertIn("**Anthropic**", out, "固有名は太字維持されるべき")

    def test_bold_with_verb_is_promoted_to_underline(self):
        """**公開** や **採用** など動詞性語を含む太字は __下線__ に昇格。

        旧 LLM プロンプト「__下線__ は動作・採用・公開などの動詞句」を rewrite_emphasis に物理化。
        """
        s = "**Anthropic** は **Claude Opus 4.8 を公開** した"
        out = rewrite_emphasis._transform_inline(s)
        self.assertIn("__Claude Opus 4.8 を公開__", out, "動詞含む太字は __下線__ に変換されるべき")
        self.assertIn("**Anthropic**", out, "固有名は太字維持されるべき")

    def test_existing_mark_and_underline_are_not_touched(self):
        """既存の ==X== / __X__ は再変換対象外（冪等性）。

        2 回適用しても結果が変わらないこと（[[feedback_check_design_principles]] §1 illegal state unrepresentable）。
        """
        s = "==重要数値 99%== と __公開__ と **Anthropic**"
        out1 = rewrite_emphasis._transform_inline(s)
        out2 = rewrite_emphasis._transform_inline(out1)
        self.assertEqual(out1, out2, "2 回目以降の rewrite で結果が変わってはいけない（冪等違反）")
        self.assertIn("==重要数値 99%==", out2)
        self.assertIn("__公開__", out2)
        self.assertIn("**Anthropic**", out2)

    def test_bold_plain_proper_noun_stays_bold(self):
        """固有名詞 (数値も動詞も含まない太字) は **太字** のまま維持される。

        プレーンな固有名・サービス名は決定打でも動作でもないので、強調記法 3 種の最下層
        （= 太字）に留め、視覚レイヤーの 3 階層を保つ。
        """
        s = "**Claude Code** と **MCP**"
        out = rewrite_emphasis._transform_inline(s)
        self.assertEqual(out, s, "固有名のみの太字は維持される")


class TestRewriteEmphasisEvent(unittest.TestCase):
    def test_rewrite_event_updates_summary_and_points(self):
        """event dict 全体の summary / summary_points を同時に変換し changed フラグが立つ。"""
        ev = {
            "summary": "**Anthropic** が **89% 達成** で **公開** した",
            "summary_points": [
                "**$15/Mtok** の価格",
                "**競合** 比較",
            ],
        }
        new_ev, changed = rewrite_emphasis.rewrite_event(ev)
        self.assertTrue(changed, "強調候補がある event は変更フラグが立つべき")
        self.assertIn("==89% 達成==", new_ev["summary"])
        self.assertIn("__公開__", new_ev["summary"])
        self.assertIn("==$15/Mtok==", new_ev["summary_points"][0])
        self.assertIn("**競合**", new_ev["summary_points"][1])  # 数値も動詞もない → 太字維持

    def test_rewrite_event_idempotent(self):
        """rewrite_event は冪等。2 回目で changed=False になる。"""
        ev = {
            "summary": "**Anthropic** が **89% 達成** で **公開** した",
            "summary_points": ["**$15/Mtok** の価格"],
        }
        new_ev, changed1 = rewrite_emphasis.rewrite_event(ev)
        self.assertTrue(changed1)
        _, changed2 = rewrite_emphasis.rewrite_event(new_ev)
        self.assertFalse(changed2, "冪等違反: 2 回目で changed が立ってはいけない")


if __name__ == "__main__":
    unittest.main()
