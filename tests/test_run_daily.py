"""日次バッチ順序の契約テスト。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import run_daily as daily  # noqa: E402


class TestRunDailyOrder(unittest.TestCase):
    def test_repo_radar_runs_after_karte_update(self):
        """Repo Radar はカルテ更新後に走る（採用候補は日次カルテ更新を待って評価する）。"""
        order: list[str] = []
        entity = {
            "entity_id": "codex",
            "name": "Codex",
            "category": "agent",
        }
        event = {
            "entity_id": "codex",
        }

        with (
            mock.patch.object(daily.collect_rss, "collect_entities",
                              return_value={"added": [event], "quality_audit_records": []}),
            mock.patch.object(daily.quality_audit, "audit_records",
                              side_effect=lambda _: order.append("quality") or {
                                  "audited": 0, "ok": 0, "warn": 0, "fail": 0,
                                  "errors": 0, "term_candidates": 0,
                              }),
            mock.patch.object(daily.schema, "validate_store",
                              return_value=([entity], [event])),
            mock.patch.object(daily, "_fast_update",
                              side_effect=lambda *_: order.append("karte")),
            mock.patch.object(daily, "_run_repo_radar_x_rss",
                              side_effect=lambda: order.append("x_rss")),
            mock.patch.object(daily.collect_repo_radar, "collect",
                              side_effect=lambda: order.append("repo_radar") or {
                                  "candidates": 0, "enriched": 0, "evaluated": 0,
                                  "skipped": 0, "degraded": 0, "ollama_errors": 0,
                              }),
            mock.patch.object(daily, "_run_buzzpost_x_rss",
                              side_effect=lambda: order.append("buzz_rss")),
            mock.patch.object(daily.collect_buzz_posts, "collect",
                              side_effect=lambda: order.append("buzzpost") or {
                                  "collected": 0, "written": 0, "degraded": 0,
                              }),
            mock.patch.object(daily, "_export_repo_radar_obsidian",
                              side_effect=lambda: order.append("obsidian")),
            mock.patch.object(daily.backfill_thumb, "backfill",
                              side_effect=lambda: order.append("thumb")),
            mock.patch.object(daily.generate_pages, "main",
                              side_effect=lambda: order.append("generate")),
            mock.patch.object(daily.time, "sleep", return_value=None),
        ):
            daily.run_daily()

        self.assertLess(order.index("karte"), order.index("x_rss"))
        self.assertLess(order.index("x_rss"), order.index("repo_radar"))
        self.assertLess(order.index("repo_radar"), order.index("obsidian"))
        self.assertLess(order.index("obsidian"), order.index("buzz_rss"))
        self.assertLess(order.index("buzz_rss"), order.index("buzzpost"))
        self.assertLess(order.index("buzzpost"), order.index("thumb"))
        self.assertEqual(order[-2:], ["thumb", "generate"])

    def test_buzzpost_rss_updates_searches_before_collecting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = root / "run_repo_radar_rss.ps1"
            search_words = root / "buzzpost-searches.json"
            updater = root / "update_buzzpost_searches.py"
            runner.write_text("", encoding="utf-8")
            updater.write_text("", encoding="utf-8")

            calls: list[list[str]] = []

            def fake_quiet_run(args, **kwargs):
                calls.append([str(arg) for arg in args])
                if "update_buzzpost_searches.py" in str(args[-1]):
                    search_words.write_text("{}", encoding="utf-8")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            with (
                mock.patch.object(daily, "TWITTER_RSS_RUNNER", runner),
                mock.patch.object(daily, "BUZZPOST_SEARCH_WORD_PATH", search_words),
                mock.patch.object(daily, "BUZZPOST_SEARCH_UPDATE_SCRIPT", updater),
                mock.patch.object(daily, "quiet_run", side_effect=fake_quiet_run),
            ):
                daily._run_buzzpost_x_rss()

        self.assertIn("update_buzzpost_searches.py", calls[0][-1])
        self.assertIn("-SearchWordPath", calls[1])
        self.assertLess(
            calls[1].index("-SearchWordPath"),
            calls[1].index("-SkipSearchUpdate"),
        )


if __name__ == "__main__":
    unittest.main()
