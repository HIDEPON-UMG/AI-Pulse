"""契約テスト: 英語見出しの自動和訳パイプライン。

なぜ重要か（意図）:
  TODAY'S THEME (h1) と各カード見出しが英語だと、UI 側の CSS line-clamp 3 で切れて意味不明
  になる事故を物理的に防ぐため、collect_rss.py の本配線で「ASCII 比率 0.95+ の見出しだけ
  llm_hybrid.translate_headline_ja で翻訳して ev["headline_ja"] に詰める」フローを契約化する。

  以下の class of bug を locked-in する:
    1. _needs_headline_ja の閾値 (0.95) が誤って下がり、日本語混在見出しまで触る
    2. translate_headline_ja の hybrid ルーティングが generate_event_extras と不一致
       （local_first で local 成功時に Gemini を呼んでしまう等の挙動分岐）
    3. local エラーが Gemini に正しくフォールバックしない（dropped）

  feedback_check_design_principles §2 (境界 1 箇所集約) + §4 (契約テスト 1 件で不変条件)。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import collect_rss  # noqa: E402
import config  # noqa: E402
import llm_gemini  # noqa: E402
import llm_hybrid  # noqa: E402
import llm_local  # noqa: E402


class TestNeedsHeadlineJa(unittest.TestCase):
    """ASCII 比率判定が「純英語のみ」を拾い「日本語混在」を触らないことを locked-in。"""

    def test_pure_english_is_needed(self):
        """純英語見出しは翻訳対象（ASCII 比率 1.0 → 0.95 以上で True）。"""
        self.assertTrue(collect_rss._needs_headline_ja(
            "Rent The Runway, Perrier Team Up For Ooh-La-La Summer 06/05/2026"
        ))

    def test_pure_japanese_is_not_needed(self):
        """純日本語見出しは触らない（ASCII 比率は記号・空白のみ → 0.95 未満）。"""
        self.assertFalse(collect_rss._needs_headline_ja(
            "Qwen 技術リード辞任の舞台裏"
        ))
        self.assertFalse(collect_rss._needs_headline_ja(
            "NVIDIA、エージェント向け CPU『Vera』を発表"
        ))

    def test_mixed_below_threshold_is_not_needed(self):
        """日本語混在（ASCII 比率 0.95 未満）は触らない。意図せず再翻訳しない。"""
        # 「AI 法案」が日本語混在で ASCII 比率は 0.95 未満
        mixed = "Japan passes AI 法案 in 2026"
        self.assertLess(collect_rss._ascii_ratio(mixed), 0.95)
        self.assertFalse(collect_rss._needs_headline_ja(mixed))

    def test_empty_is_not_needed(self):
        """空文字は触らない（_ascii_ratio が 0.0 を返す境界）。"""
        self.assertFalse(collect_rss._needs_headline_ja(""))


class TestTranslateHeadlineJaHybridRouting(unittest.TestCase):
    """translate_headline_ja の hybrid 分岐が generate_event_extras と同じルートを通る。"""

    def setUp(self) -> None:
        self._orig_mode = config.HYBRID_MODE
        config.HYBRID_MODE = "local_first"

    def tearDown(self) -> None:
        config.HYBRID_MODE = self._orig_mode

    def test_local_success_does_not_call_gemini(self):
        """local が成功した時は Gemini を呼ばない（クォータ温存・local を必ず 1 度試す）。"""
        with patch.object(llm_local, "translate_headline_ja", return_value="ローカル翻訳") as ml, \
             patch.object(llm_gemini, "translate_headline_ja") as mg:
            result = llm_hybrid.translate_headline_ja("Some English Headline")
        self.assertEqual(result, "ローカル翻訳")
        self.assertEqual(ml.call_count, 1)
        self.assertEqual(mg.call_count, 0)

    def test_local_error_falls_back_to_gemini(self):
        """local が LLMError を投げたら Gemini にフォールバック（drop しない）。"""
        with patch.object(
            llm_local, "translate_headline_ja",
            side_effect=llm_gemini.LLMError("Ollama 接続失敗"),
        ) as ml, \
             patch.object(llm_gemini, "translate_headline_ja", return_value="Gemini 翻訳") as mg:
            result = llm_hybrid.translate_headline_ja("Some English Headline")
        self.assertEqual(result, "Gemini 翻訳")
        self.assertEqual(ml.call_count, 1)
        self.assertEqual(mg.call_count, 1)

    def test_gemini_only_mode_always_uses_gemini(self):
        """HYBRID_MODE=gemini_only はローカル状態に関わらず常時 Gemini。"""
        config.HYBRID_MODE = "gemini_only"
        with patch.object(llm_local, "translate_headline_ja") as ml, \
             patch.object(llm_gemini, "translate_headline_ja", return_value="Gemini 翻訳") as mg:
            result = llm_hybrid.translate_headline_ja("Some English Headline")
        self.assertEqual(result, "Gemini 翻訳")
        self.assertEqual(ml.call_count, 0)
        self.assertEqual(mg.call_count, 1)

    def test_local_only_mode_never_calls_gemini(self):
        """HYBRID_MODE=local_only は Gemini を呼ばず、local 失敗時はそのまま raise。"""
        config.HYBRID_MODE = "local_only"
        with patch.object(
            llm_local, "translate_headline_ja",
            side_effect=llm_gemini.LLMError("Ollama 接続失敗"),
        ) as ml, \
             patch.object(llm_gemini, "translate_headline_ja") as mg:
            with self.assertRaises(llm_gemini.LLMError):
                llm_hybrid.translate_headline_ja("Some English Headline")
        self.assertEqual(ml.call_count, 1)
        self.assertEqual(mg.call_count, 0)


class TestTranslateHeadlineJaEntityContext(unittest.TestCase):
    """entity_context が下流の llm_local / llm_gemini に正しく伝播することを確認。"""

    def setUp(self) -> None:
        self._orig_mode = config.HYBRID_MODE
        config.HYBRID_MODE = "local_first"

    def tearDown(self) -> None:
        config.HYBRID_MODE = self._orig_mode

    def test_entity_context_propagates_to_local(self):
        """entity_context kwarg が llm_local まで届く（固有名詞ヒント維持）。"""
        captured = {}

        def fake_local(headline, *, entity_context=None):
            captured["headline"] = headline
            captured["entity_context"] = entity_context
            return "ダミー翻訳"

        ent = {"entity_name": "Qwen", "vendor": "Alibaba Cloud"}
        with patch.object(llm_local, "translate_headline_ja", side_effect=fake_local):
            llm_hybrid.translate_headline_ja("Qwen 3.7 Released", entity_context=ent)
        self.assertEqual(captured["headline"], "Qwen 3.7 Released")
        self.assertEqual(captured["entity_context"], ent)


if __name__ == "__main__":
    unittest.main()
