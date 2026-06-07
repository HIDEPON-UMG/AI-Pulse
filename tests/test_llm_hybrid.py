"""契約テスト: llm_hybrid.generate_event_extras のフォールバック挙動。

なぜ重要か（意図）:
  Gemini Free Tier クォータ天井（RPD/RPM）と「データ学習利用」を回避するため、抽出はローカル LLM
  (Qwen3.6-27B IQ3_XXS) を優先し、Ollama 接続失敗 / 空応答 / schema 違反尽き（LLMError）の時のみ
  Gemini にフォールバックする。境界 1 箇所 (llm_hybrid) で切替を locked-in するため、以下の
  class of bug を構造的に封じる:
    1. local 経由が正常成功した時は Gemini を呼ばない（クォータ温存）
    2. local の LLMError では即 Gemini にフォールバックする（drop されない）
    3. local_first は GPU 状態を事前推測せず、必ず local を 1 度試す
       （2026-06-07 撤廃した _gpu_busy 事前スキップが再混入すると 1 のテストで落ちる）
    4. HYBRID_MODE=gemini_only は常時 Gemini を呼ぶ（緊急回避手段）

  feedback_check_design_principles §1 (illegal state unrepresentable: 誤りうる GPU 占有事前判定を
  撤廃) + §2 (境界 1 箇所集約) + §4 (契約テスト 1 件で不変条件 locked-in)。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import config  # noqa: E402
import llm_gemini  # noqa: E402
import llm_hybrid  # noqa: E402
import llm_local  # noqa: E402

_VALID_PAYLOAD_LOCAL = {
    "summary": "ローカル LLM が返したサンプル要約です。" + "あ" * 80,
    "summary_points": [
        "ローカル要点A 詳細を述べる",
        "ローカル要点B 詳細を述べる",
        "ローカル要点C 詳細を述べる",
    ],
    "rationale": {
        "importance": "重要度を高と判定する根拠の文章サンプル本文 (20 字以上の文章要件を満たす)",
        "impact": "影響度を高と判定する根拠の文章サンプル本文 (20 字以上の文章要件を満たす)",
        "buzz": "話題性を高と判定する根拠の文章サンプル本文 (20 字以上の文章要件を満たす)",
    },
    "score": 72,
    "importance": "high",
    "event_type": "release",
}

_VALID_PAYLOAD_GEMINI = {**_VALID_PAYLOAD_LOCAL, "score": 88, "summary": "Gemini が返したサンプル要約です。" + "あ" * 80}

_META = {
    "title": "サンプル見出し",
    "entity_name": "Claude Opus",
    "category": "model",
    "vendor": "Anthropic",
    "entity_positioning": "Anthropic の最上位 LLM",
}


class TestHybridLocalFirst(unittest.TestCase):
    """HYBRID_MODE=local_first (デフォルト) のフォールバック挙動。"""

    def setUp(self) -> None:
        self._orig_mode = config.HYBRID_MODE
        config.HYBRID_MODE = "local_first"

    def tearDown(self) -> None:
        config.HYBRID_MODE = self._orig_mode

    def test_local_success_does_not_call_gemini(self):
        """local が正常成功した時は Gemini を 1 度も呼ばない（クォータ温存）。

        併せて「local_first は GPU 状態を事前推測せず必ず local を 1 度試す」を担保する。
        _gpu_busy 的な事前スキップが再混入すると local が呼ばれず Gemini に倒れてここで落ちる。
        """
        with patch.object(llm_local, "generate_event_extras", return_value=_VALID_PAYLOAD_LOCAL) as mock_local, \
             patch.object(llm_gemini, "generate_event_extras") as mock_gemini:
            result = llm_hybrid.generate_event_extras("本文" * 200, _META)
        self.assertEqual(result["score"], 72, "local の payload がそのまま返るべき")
        self.assertEqual(mock_local.call_count, 1, "local_first は事前スキップせず必ず local を試すべき")
        self.assertEqual(mock_gemini.call_count, 0, "local 成功時に Gemini を呼んではいけない")

    def test_local_error_falls_back_to_gemini(self):
        """local が LLMError を投げたら Gemini にフォールバックして返す。"""
        with patch.object(llm_local, "generate_event_extras", side_effect=llm_gemini.LLMError("Ollama 接続失敗")) as mock_local, \
             patch.object(llm_gemini, "generate_event_extras", return_value=_VALID_PAYLOAD_GEMINI) as mock_gemini:
            result = llm_hybrid.generate_event_extras("本文" * 200, _META)
        self.assertEqual(result["score"], 88, "Gemini の payload がフォールバックで返るべき")
        self.assertEqual(mock_local.call_count, 1)
        self.assertEqual(mock_gemini.call_count, 1)


class TestHybridModeOverrides(unittest.TestCase):
    """HYBRID_MODE の他値（gemini_only / local_only）が回避手段として動くこと。"""

    def setUp(self) -> None:
        self._orig_mode = config.HYBRID_MODE

    def tearDown(self) -> None:
        config.HYBRID_MODE = self._orig_mode

    def test_gemini_only_always_calls_gemini(self):
        """HYBRID_MODE=gemini_only はローカル状態に関わらず常時 Gemini を呼ぶ。

        Ollama 全停止時の暫定回避や Gemini A/B 比較用の locked-in 手段。
        """
        config.HYBRID_MODE = "gemini_only"
        with patch.object(llm_local, "generate_event_extras") as mock_local, \
             patch.object(llm_gemini, "generate_event_extras", return_value=_VALID_PAYLOAD_GEMINI) as mock_gemini:
            result = llm_hybrid.generate_event_extras("本文" * 200, _META)
        self.assertEqual(result["score"], 88)
        self.assertEqual(mock_local.call_count, 0)
        self.assertEqual(mock_gemini.call_count, 1)

    def test_local_only_never_calls_gemini(self):
        """HYBRID_MODE=local_only は Gemini を呼ばず、local 失敗時は素直に raise する。"""
        config.HYBRID_MODE = "local_only"
        with patch.object(llm_local, "generate_event_extras", side_effect=llm_gemini.LLMError("Ollama 接続失敗")) as mock_local, \
             patch.object(llm_gemini, "generate_event_extras") as mock_gemini:
            with self.assertRaises(llm_gemini.LLMError):
                llm_hybrid.generate_event_extras("本文" * 200, _META)
        self.assertEqual(mock_local.call_count, 1)
        self.assertEqual(mock_gemini.call_count, 0)


if __name__ == "__main__":
    unittest.main()
