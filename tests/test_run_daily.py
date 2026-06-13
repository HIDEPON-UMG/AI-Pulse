"""日次バッチ順序の契約テスト。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
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
            mock.patch.object(daily.backfill_thumb, "backfill",
                              side_effect=lambda: order.append("thumb")),
            mock.patch.object(daily.generate_pages, "main",
                              side_effect=lambda: order.append("generate")),
            mock.patch.object(daily.time, "sleep", return_value=None),
        ):
            daily.run_daily()

        self.assertLess(order.index("karte"), order.index("x_rss"))
        self.assertLess(order.index("x_rss"), order.index("repo_radar"))
        self.assertEqual(order[-2:], ["thumb", "generate"])


if __name__ == "__main__":
    unittest.main()
