"""llm_hybrid の provider counter 契約テスト。

なぜ重要か (意図):
  llm_hybrid は local_first で「ローカル Ollama 失敗 → 即 Gemini」を silent fallback する設計のため、
  外から「Gemini が何回呼ばれたか」が見えない。Ollama サーバ落ち / GPU 占有が続いていると
  「全件 Gemini で動いているのに成功扱い」になり、無料クォータ消費と Google 学習データ提供が
  静かに進行する事故が起こり得る。

  本テストは provider counter (_STATS) の不変条件を locked-in する
  ([[feedback_check_design_principles]] §4 契約テスト 1 件で class of bug を封じる):
    1. reset_stats() で全カウンタがゼロに戻る
    2. local_only / gemini_only モードで provider が正しく記録される
    3. local_first で GPU 占有時は gpu_busy_to_gemini に分類される
    4. local_first で local 成功は local に記録される
    5. local_first で local 失敗 → Gemini 経路は local_fail_to_gemini に分類される
    6. gemini / local の和が「成功呼出回数」を表す不変条件

  llm_local / llm_gemini の本物呼出は行わず unittest.mock で provider を差し替える
  (= ネットワーク非依存 / Ollama 起動状態に依存しない)。
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import config  # noqa: E402
import llm_hybrid  # noqa: E402


_DUMMY_EXTRAS = {
    "summary": "x",
    "summary_points": ["x"],
    "rationale": {"why_important": "x", "what_changes": "x", "for_whom": "x"},
    "score": 5,
    "importance": "中",
    "event_type": "release",
}


class TestLlmHybridStats(unittest.TestCase):
    def setUp(self):
        llm_hybrid.reset_stats()

    def test_reset_stats_zeroes_all_counters(self):
        """reset_stats() が全カウンタを 0 に戻す。

        この性質が崩れると collect_rss のバッチ単位集計が前回分を引き継いでしまい、
        累積比率が偽の値で WARN を撃ち続ける / 撃たない事故に直結する。
        """
        # 直接書込んでテスト用に汚す
        for k in llm_hybrid._STATS:
            llm_hybrid._STATS[k] = 7
        llm_hybrid.reset_stats()
        stats = llm_hybrid.get_stats()
        for k, v in stats.items():
            self.assertEqual(v, 0, f"reset 後に {k}={v} がゼロでない")

    def test_get_stats_returns_copy(self):
        """get_stats() が defensive copy を返す (呼出側からの破壊的変更を防ぐ)。"""
        stats = llm_hybrid.get_stats()
        stats["local"] = 999
        self.assertEqual(llm_hybrid.get_stats()["local"], 0)

    def test_local_only_mode_records_local(self):
        """HYBRID_MODE=local_only で local counter のみ増える (Gemini は呼ばれない)。"""
        with patch.object(config, "HYBRID_MODE", "local_only"), \
             patch.object(llm_hybrid.llm_local, "generate_event_extras",
                          return_value=_DUMMY_EXTRAS):
            llm_hybrid.generate_event_extras("body", {"title": "t"})
        stats = llm_hybrid.get_stats()
        self.assertEqual(stats["local"], 1)
        self.assertEqual(stats["gemini"], 0)

    def test_gemini_only_mode_records_gemini(self):
        """HYBRID_MODE=gemini_only で gemini counter のみ増える (local は呼ばれない)。"""
        with patch.object(config, "HYBRID_MODE", "gemini_only"), \
             patch.object(llm_hybrid.llm_gemini, "generate_event_extras",
                          return_value=_DUMMY_EXTRAS):
            llm_hybrid.generate_event_extras("body", {"title": "t"})
        stats = llm_hybrid.get_stats()
        self.assertEqual(stats["gemini"], 1)
        self.assertEqual(stats["local"], 0)
        # 内訳カウンタは「GPU 占有起因」「local 失敗起因」のいずれでもないため 0 のまま
        self.assertEqual(stats["gpu_busy_to_gemini"], 0)
        self.assertEqual(stats["local_fail_to_gemini"], 0)

    def test_local_first_gpu_busy_routes_to_gemini(self):
        """local_first で GPU 占有時は local を試さず直接 Gemini に流す。

        gpu_busy_to_gemini が +1 され、local は +0 になる。これを観測できないと
        「local Ollama が動いていないのに気付かず全件 Gemini」事故が静かに進行する。
        """
        with patch.object(config, "HYBRID_MODE", "local_first"), \
             patch.object(llm_hybrid.llm_gemini, "generate_event_extras",
                          return_value=_DUMMY_EXTRAS):
            # gpu_probe を「9999 MB 使用中」に差し替え (= 6000 MB 閾値超)
            llm_hybrid.generate_event_extras("body", {"title": "t"},
                                             gpu_probe=lambda: 9999)
        stats = llm_hybrid.get_stats()
        self.assertEqual(stats["gemini"], 1)
        self.assertEqual(stats["gpu_busy_to_gemini"], 1)
        self.assertEqual(stats["local"], 0)
        self.assertEqual(stats["local_fail_to_gemini"], 0)

    def test_local_first_local_success_records_local(self):
        """local_first で GPU 非占有 + local 成功は local に記録 (Gemini は呼ばれない)。"""
        with patch.object(config, "HYBRID_MODE", "local_first"), \
             patch.object(llm_hybrid.llm_local, "generate_event_extras",
                          return_value=_DUMMY_EXTRAS):
            llm_hybrid.generate_event_extras("body", {"title": "t"},
                                             gpu_probe=lambda: 0)
        stats = llm_hybrid.get_stats()
        self.assertEqual(stats["local"], 1)
        self.assertEqual(stats["gemini"], 0)
        self.assertEqual(stats["gpu_busy_to_gemini"], 0)
        self.assertEqual(stats["local_fail_to_gemini"], 0)

    def test_local_first_local_fail_records_local_fail_to_gemini(self):
        """local_first で local 失敗 → Gemini で救った経路は local_fail_to_gemini で記録。"""
        with patch.object(config, "HYBRID_MODE", "local_first"), \
             patch.object(llm_hybrid.llm_local, "generate_event_extras",
                          side_effect=llm_hybrid.LLMError("ollama down")), \
             patch.object(llm_hybrid.llm_gemini, "generate_event_extras",
                          return_value=_DUMMY_EXTRAS):
            llm_hybrid.generate_event_extras("body", {"title": "t"},
                                             gpu_probe=lambda: 0)
        stats = llm_hybrid.get_stats()
        self.assertEqual(stats["gemini"], 1)
        self.assertEqual(stats["local_fail_to_gemini"], 1)
        self.assertEqual(stats["local"], 0)
        self.assertEqual(stats["gpu_busy_to_gemini"], 0)

    def test_translate_headline_ja_also_records(self):
        """translate_headline_ja も counter を更新する (generate_event_extras と同じ契約)。

        この関数だけ計測から漏れると、見出し翻訳が Gemini に流れているのを見落とす。
        """
        with patch.object(config, "HYBRID_MODE", "local_only"), \
             patch.object(llm_hybrid.llm_local, "translate_headline_ja",
                          return_value="日本語見出し"):
            llm_hybrid.translate_headline_ja("English headline")
        self.assertEqual(llm_hybrid.get_stats()["local"], 1)

    def test_regenerate_rationale_also_records(self):
        """regenerate_rationale も counter を更新する (generate_event_extras と同じ契約)。"""
        with patch.object(config, "HYBRID_MODE", "gemini_only"), \
             patch.object(llm_hybrid.llm_gemini, "regenerate_rationale",
                          return_value={"why_important": "x", "what_changes": "x", "for_whom": "x"}):
            llm_hybrid.regenerate_rationale("h", "s", ["p"], "中")
        self.assertEqual(llm_hybrid.get_stats()["gemini"], 1)

    def test_failure_does_not_increment_counters(self):
        """両経路失敗で LLMError を投げた場合は counter を増分しない。

        失敗を「成功呼出回数」の分母に入れてしまうと比率が歪み、WARN ロジックの精度が落ちる。
        """
        with patch.object(config, "HYBRID_MODE", "local_first"), \
             patch.object(llm_hybrid.llm_local, "generate_event_extras",
                          side_effect=llm_hybrid.LLMError("ollama down")), \
             patch.object(llm_hybrid.llm_gemini, "generate_event_extras",
                          side_effect=llm_hybrid.LLMError("gemini quota")):
            with self.assertRaises(llm_hybrid.LLMError):
                llm_hybrid.generate_event_extras("body", {"title": "t"},
                                                 gpu_probe=lambda: 0)
        stats = llm_hybrid.get_stats()
        self.assertEqual(stats["local"], 0)
        self.assertEqual(stats["gemini"], 0)


if __name__ == "__main__":
    unittest.main()
