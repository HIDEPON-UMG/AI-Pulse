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


class TestAddEmphasisInline(unittest.TestCase):
    """add_emphasis_event の決定論付与ロジック。

    なぜ重要か（意図）:
      2026-06-05 追補11 で extract_grounded.md (新 prompt) を「プレーンテキスト出力」に切替えた結果、
      新規 entry は強調記法を一切持たない状態になり、UI の 3 種視覚レイヤー（黄マーカー / 波線下線 / 太字）が
      無効化された。本テストは class of bug を 4 件で固定する:
        1. プレーンテキスト中の数値表現は ==マーカー== で囲まれる
        2. プレーンテキスト中の動詞性語は __下線__ で囲まれる
        3. entity_context から渡された固有名候補は **太字** で囲まれる
        4. 既存記法 (==/__/**) の内側は再付与されない（冪等性 + non-overlapping）
    """

    def test_plain_number_gets_mark(self):
        """プレーンテキスト中の数値表現 (89% / $7B / 3 倍 など) は ==マーカー== に。"""
        s = "Devin で 89% 上回り を達成"
        out = rewrite_emphasis._add_inline_emphasis(s)
        self.assertIn("==89%==", out, "%系数値はマーカー化される")

    def test_plain_verb_gets_underline(self):
        """プレーンテキスト中の動詞性語 (リリース / 発表 / 採用 など) は __下線__ に。"""
        s = "Anthropic は Claude Opus 4.8 をリリースしました"
        out = rewrite_emphasis._add_inline_emphasis(s)
        self.assertIn("__リリース__", out, "動詞性語は下線化される")

    def test_proper_noun_gets_bold_when_in_context(self):
        """entity_context.name / vendor / competitors[].name は **太字** に。"""
        s = "Anthropic は Claude Opus を発表"
        out = rewrite_emphasis._add_inline_emphasis(
            s, proper_nouns=["Anthropic", "Claude Opus"]
        )
        self.assertIn("**Anthropic**", out, "vendor 名は太字化される")
        self.assertIn("**Claude Opus**", out, "entity 名は太字化される")
        self.assertIn("__発表__", out, "動詞は下線化される（共存）")

    def test_no_double_wrap_inside_existing_markup(self):
        """既存 ==X== / __X__ / **X** の内側は再付与されない（non-overlapping）。"""
        # 既に ==89%== / __リリース__ / **Anthropic** が付いている文字列
        s = "==89%== の **Anthropic** が __リリース__ した"
        out = rewrite_emphasis._add_inline_emphasis(
            s, proper_nouns=["Anthropic"]
        )
        # 二重に囲まれていないか確認（=== や ==== が出現したら二重）
        self.assertNotIn("====", out, "数値が二重マーカー化されてはいけない")
        self.assertNotIn("****", out, "固有名が二重太字化されてはいけない")
        self.assertNotIn("____", out, "動詞が二重下線化されてはいけない")

    def test_add_emphasis_is_idempotent(self):
        """add_emphasis_event を 2 回適用しても結果が変わらない（冪等性）。"""
        s = "Anthropic は 89% の精度を達成し Claude Opus 4.8 をリリースしました"
        proper = ["Anthropic", "Claude Opus 4.8"]
        out1 = rewrite_emphasis._add_inline_emphasis(s, proper_nouns=proper)
        out2 = rewrite_emphasis._add_inline_emphasis(out1, proper_nouns=proper)
        self.assertEqual(out1, out2, "2 回目以降の付与で結果が変わってはいけない（冪等違反）")


class TestAddEmphasisEvent(unittest.TestCase):
    def test_add_emphasis_event_uses_entity_context(self):
        """add_emphasis_event は entity_context から固有名を抽出し付与する。"""
        ev = {
            "summary": "Anthropic は Claude Opus 4.8 をリリースし 89% のスコアを達成",
            "summary_points": [
                "Claude Opus 4.8 が新リリース",
                "ベンチマークで 89% を記録",
            ],
        }
        entity_context = {
            "name": "Claude Opus 4.8",
            "vendor": "Anthropic",
            "competitors": [{"name": "GPT-5"}],
        }
        new_ev, changed = rewrite_emphasis.add_emphasis_event(
            ev, entity_context=entity_context
        )
        self.assertTrue(changed, "強調候補がある event は変更フラグが立つべき")
        self.assertIn("**Anthropic**", new_ev["summary"], "vendor が太字化される")
        self.assertIn("**Claude Opus 4.8**", new_ev["summary"], "entity name が太字化される")
        self.assertIn("__リリース__", new_ev["summary"], "動詞が下線化される")
        self.assertIn("==89%==", new_ev["summary"], "数値がマーカー化される")
        self.assertIn("**Claude Opus 4.8**", new_ev["summary_points"][0])
        self.assertIn("==89%==", new_ev["summary_points"][1])

    def test_add_emphasis_event_idempotent(self):
        """add_emphasis_event を 2 回呼んでも changed=False になる（冪等）。"""
        ev = {
            "summary": "Anthropic は 89% を達成しリリースした",
            "summary_points": ["89% のスコア"],
        }
        ctx = {"name": "Claude Opus", "vendor": "Anthropic"}
        new_ev, changed1 = rewrite_emphasis.add_emphasis_event(ev, entity_context=ctx)
        self.assertTrue(changed1, "1 回目は changed=True")
        _, changed2 = rewrite_emphasis.add_emphasis_event(new_ev, entity_context=ctx)
        self.assertFalse(changed2, "冪等違反: 2 回目で changed が立ってはいけない")

    def test_extract_proper_nouns_dedup_and_long_first(self):
        """_extract_proper_nouns は重複削除 + 長一致優先で並べる。"""
        ctx = {
            "name": "Claude Opus 4.8",
            "vendor": "Anthropic",
            "offering": "Claude Opus 4.8",  # name と重複
            "competitors": [{"name": "GPT-5"}, "Gemini Ultra"],
            "relations": [{"name": "Anthropic"}],  # vendor と重複
        }
        nouns = rewrite_emphasis._extract_proper_nouns(ctx)
        # 重複削除
        self.assertEqual(len(set(nouns)), len(nouns), "固有名候補は重複しない")
        # 長一致優先（長い方が先）
        for i in range(len(nouns) - 1):
            self.assertGreaterEqual(
                len(nouns[i]), len(nouns[i + 1]),
                "長一致優先のため長い順にソートされる"
            )

    def test_add_emphasis_event_no_context_only_numbers_and_verbs(self):
        """entity_context が None でも数値と動詞は付与される（固有名のみスキップ）。"""
        ev = {
            "summary": "新サービスを 89% の精度でリリースした",
            "summary_points": ["89% 精度を記録"],
        }
        new_ev, changed = rewrite_emphasis.add_emphasis_event(ev, entity_context=None)
        self.assertTrue(changed, "数値・動詞があれば付与される")
        self.assertIn("==89%==", new_ev["summary"])
        self.assertIn("__リリース__", new_ev["summary"])


if __name__ == "__main__":
    unittest.main()
