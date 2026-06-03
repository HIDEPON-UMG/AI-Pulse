"""契約テスト: llm_gemini.generate_event_extras の不変条件 3 件。

なぜ重要か（意図）:
  Gemini 呼び出しのリトライ／レート制御／失敗時ドロップを境界 1 箇所（llm_gemini）に集約した
  以上、そこが壊れたら全 95 件/日の品質が一気に崩れる。class of bug を 3 件で固定する:
    1. schema 違反は 1 回だけ追記再投げして 2 回目で諦める（無限リトライさせない）
    2. RPM トークンバケットが超過時に正しくブロックする（バースト 429 を防ぐ）
    3. 連続 5xx でリトライ尽きたら例外を上に飛ばす（None で ingest に漏れない）
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import config  # noqa: E402
import llm_gemini  # noqa: E402
from rate_limiter import TokenBucket  # noqa: E402

_VALID_PAYLOAD = {
    "summary": "サンプル要約です" + "あ" * 20,
    "summary_points": ["要点A 詳細サンプル", "要点B 詳細サンプル", "要点C 詳細サンプル"],
    "rationale": {"importance": "重要度の根拠サンプル", "impact": "影響度の根拠サンプル", "buzz": "話題性の根拠サンプル"},
    "score": 70,
    "importance": "high",
    "event_type": "release",
}

_META = {
    "title": "サンプル見出し",
    "entity_name": "Claude Opus",
    "category": "model",
    "vendor": "Anthropic",
    "entity_positioning": "Anthropic の最上位 LLM",
}

# Gemini への実 API 呼び出しを避けるため、_load_api_key / _call_once / _get_bucket を差し替える


def _make_bucket() -> TokenBucket:
    """テストごとに新しいバケットを返す（モジュール内の _bucket をリセット）。"""
    llm_gemini._bucket = None
    return llm_gemini._get_bucket()


class TestLLMGeminiContract(unittest.TestCase):
    def setUp(self) -> None:
        llm_gemini._bucket = None  # バケットリセット
        llm_gemini._client = None  # クライアントリセット（API キー読込を回避）

    def test_schema_violation_retries_once(self):
        """summary_points が 2 件 → 1 回再投げ → 4 件で OK → ok。

        2 件のままだったら 2 回目で諦めて LLMError。
        """
        bad = {**_VALID_PAYLOAD, "summary_points": ["短い1", "短い2"]}  # 2 件
        good = {**_VALID_PAYLOAD, "summary_points": ["要点A 詳細", "要点B 詳細", "要点C 詳細", "要点D 詳細"]}
        responses = [bad, good]

        def fake_call(article_text, meta, *, extra_instruction=""):
            return responses.pop(0)

        with patch.object(llm_gemini, "_call_once", side_effect=fake_call):
            result = llm_gemini.generate_event_extras("本文" * 200, _META)
        self.assertEqual(len(result["summary_points"]), 4)
        self.assertEqual(responses, [])  # 2 回ぴったり使い切る

        # 2 回連続 schema 違反は LLMError
        bad2 = [{**_VALID_PAYLOAD, "summary_points": ["短い1", "短い2"]}] * 3

        def fake_bad(article_text, meta, *, extra_instruction=""):
            return bad2.pop(0)

        with patch.object(llm_gemini, "_call_once", side_effect=fake_bad):
            with self.assertRaises(llm_gemini.LLMError):
                llm_gemini.generate_event_extras("本文" * 200, _META)

    def test_rate_limit_blocks_until_token(self):
        """capacity を超える acquire は実時間待ちが発生する（バーストで 429 を踏まない）。

        rpm=60 / capacity=2 のバケットに 3 回 acquire すると 3 回目で 1 秒前後待たされる。
        """
        bucket = TokenBucket(rpm=60, capacity=2)  # 1 token/sec, capacity 2
        bucket.acquire()  # 即時
        bucket.acquire()  # 即時
        start = time.monotonic()
        waited = bucket.acquire()
        elapsed = time.monotonic() - start
        # capacity 使い切り後は 1 token 補充に 1 秒かかるので 0.5 秒以上待つはず
        self.assertGreater(waited, 0.5, f"waited={waited} (expected > 0.5s blocking)")
        self.assertGreater(elapsed, 0.5, f"elapsed={elapsed}")

    def test_failure_drops_candidate(self):
        """連続して transient 例外（503）を返したらリトライ尽きで LLMError。ingest 側に None で届かない。"""
        class FakeServerError(Exception):
            pass

        calls = {"n": 0}

        def fake_call(article_text, meta, *, extra_instruction=""):
            calls["n"] += 1
            raise FakeServerError("503 UNAVAILABLE")

        with patch.object(llm_gemini, "_call_once", side_effect=fake_call):
            # time.sleep をスキップしてテスト時間を短縮
            with patch.object(llm_gemini.time, "sleep", lambda s: None):
                with self.assertRaises(llm_gemini.LLMError):
                    llm_gemini.generate_event_extras("本文" * 200, _META)
        # GEMINI_MAX_RETRIES + 1 回試行する
        self.assertEqual(calls["n"], config.GEMINI_MAX_RETRIES + 1)


if __name__ == "__main__":
    unittest.main()
