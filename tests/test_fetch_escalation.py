from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import fetch_escalation  # noqa: E402


class TestFetchEscalation(unittest.TestCase):
    def setUp(self) -> None:
        fetch_escalation._stealthy_used = 0

    def test_rejects_non_http_scheme(self):
        """http(s) 以外は昇格前に拒否する。"""
        result = fetch_escalation.fetch_with_escalation("file:///tmp/x")

        self.assertFalse(result.ok)
        self.assertEqual(result.stage, "guard")
        self.assertEqual(result.attempts[0][0], "guard")

    def test_urllib_success_does_not_escalate(self):
        """urllib で成功したら Scrapling へ昇格しない。"""
        with patch.object(fetch_escalation, "_fetch_urllib",
                          return_value=(200, "<html>ok</html>", "ok")) as urllib_fetch:
            with patch.object(fetch_escalation, "_fetch_scrapling") as scrapling_fetch:
                result = fetch_escalation.fetch_with_escalation("https://example.com")

        self.assertTrue(result.ok)
        self.assertEqual(result.stage, "urllib")
        urllib_fetch.assert_called_once()
        scrapling_fetch.assert_not_called()

    def test_blocked_response_escalates_to_fetcher(self):
        """blocked 判定なら Fetcher へ昇格する。"""
        with patch.object(fetch_escalation, "_fetch_urllib",
                          return_value=(403, "<html>blocked</html>", "http error: 403")):
            with patch.object(fetch_escalation, "_fetch_scrapling",
                              return_value=(200, "<html>rescued</html>", "ok")) as scrapling_fetch:
                result = fetch_escalation.fetch_with_escalation("https://example.com")

        self.assertTrue(result.ok)
        self.assertEqual(result.stage, "fetcher")
        scrapling_fetch.assert_called_once_with("https://example.com", 20.0, stealthy=False)

    def test_stealthy_budget_zero_blocks_browser_stage(self):
        """StealthyFetcher 予算 0 ならブラウザ段を呼ばない。"""
        with patch.object(fetch_escalation, "_fetch_urllib",
                          return_value=(403, "<html>blocked</html>", "http error: 403")):
            with patch.object(fetch_escalation, "_fetch_scrapling",
                              return_value=(403, "<html>cloudflare</html>", "blocked")) as scrapling_fetch:
                result = fetch_escalation.fetch_with_escalation(
                    "https://example.com", stealthy_budget=0
                )

        self.assertFalse(result.ok)
        self.assertEqual(result.stage, "fetcher")
        self.assertIn("上限 0 件", result.error or "")
        scrapling_fetch.assert_called_once_with("https://example.com", 20.0, stealthy=False)


if __name__ == "__main__":
    unittest.main()
