"""契約テスト: 抽出段階の関連性ゲート（同名異義・無関係記事を event 化しない）。

なぜ重要か（意図）:
  2026-06-06 に runway カテゴリで「Rent the Runway（ファッション）/ 空港の滑走路 /
  ファッションショーのランウェイ」等 AI ゼロの記事が混入した。当時の対策は
  collect_rss.build_query() の検索クエリを AI 文脈に絞る「入力側」だけだったが、
  Google News RSS はクエリを緩く解釈するため同名異義の無関係記事を返し続け、再発した。

  本テストは「出力側ゲート」を locked-in する:
    1. 抽出スキーマ (schema.gemini_response_schema) が is_relevant を required で持つ
       → local/Gemini 両方の構造化出力に is_relevant が強制される（境界 1 箇所集約 §2）
    2. collect_rss.collect_entities が is_relevant=False の記事を event 化しない
       → 無関係記事が data/events.jsonl に入れない（§1 illegal state unrepresentable）

  入力側 (test_collect_rss_query.py) + 出力側 (本テスト) の二段で
  「異義語 entity に AI 無関係記事が混入する class of bugs」を構造的に封じる
  ([[feedback_check_design_principles]] §1/§2/§4)。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import collect_rss  # noqa: E402
import schema  # noqa: E402


class TestRelevanceSchema(unittest.TestCase):
    """抽出スキーマが is_relevant を強制すること（local/Gemini 共通の単一ソース）。"""

    def test_schema_requires_is_relevant(self):
        s = schema.gemini_response_schema()
        self.assertIn("is_relevant", s["required"], "is_relevant が required に無い")
        self.assertEqual(s["properties"]["is_relevant"]["type"], "boolean")

    def test_schema_has_relevance_reason(self):
        s = schema.gemini_response_schema()
        self.assertIn("relevance_reason", s["properties"], "relevance_reason が properties に無い")


class TestRelevanceGate(unittest.TestCase):
    """collect_entities が is_relevant=False の記事を event 化しないこと。"""

    _ENTITY = {
        "entity_id": "runway", "name": "Runway", "category": "media",
        "vendor": "Runway", "positioning": "プロ向け動画生成 AI",
        "search_query": "Runway AI video generation",
    }
    _ITEM = {
        "title": "Rent The Runway, Perrier Team Up For Summer",
        "link": "https://example.com/fashion-rental",
        "rss_summary": "fashion rental partnership",
        "date": "2026-06-07",
        "source_name": "Fashion Wire",
        "source_url_hint": "https://example.com/fashion-rental",
    }
    _ARTICLE = {
        "text": "Rent the Runway, the clothing rental company, announced a summer partnership. " * 8,
        "publisher_url": "https://example.com/fashion-rental",
        "publisher_name": "Fashion Wire",
        "og_image": None,
    }
    _IRRELEVANT_EXTRAS = {
        "is_relevant": False,
        "relevance_reason": "ファッションレンタル Rent the Runway で AI と無関係",
        "summary": "あ" * 40,
        "summary_points": ["要点A詳細", "要点B詳細", "要点C詳細"],
        "rationale": {"importance": "理由" * 6, "impact": "理由" * 6, "buzz": "理由" * 6},
        "score": 10, "importance": "low", "event_type": "release",
    }

    def _run_collect(self, extras: dict):
        """collect_entities を全依存モックで 1 entity / 1 記事だけ走らせる。"""
        with patch.object(collect_rss.schema, "validate_store", return_value=([self._ENTITY], [])), \
             patch.object(collect_rss, "_fetch_rss", return_value=[self._ITEM]), \
             patch.object(collect_rss.fetch_article, "extract", return_value=self._ARTICLE), \
             patch.object(collect_rss.llm_hybrid, "generate_event_extras", return_value=extras), \
             patch.object(collect_rss.llm_hybrid, "translate_headline_ja", return_value="翻訳済み見出し"), \
             patch.object(collect_rss.store, "ingest_events",
                          return_value={"added": [], "skipped_dup": 0, "skipped_score": 0}) as mock_ingest, \
             patch.object(collect_rss.time, "sleep"):
            result = collect_rss.collect_entities()
        # ingest_events(entities_path, events_path, candidates) の第3引数を回収
        passed_candidates = mock_ingest.call_args[0][2]
        return result, passed_candidates

    def test_irrelevant_article_is_not_turned_into_event(self):
        """is_relevant=False の記事は skipped_irrelevant にカウントされ candidates に入らない。"""
        result, candidates = self._run_collect(self._IRRELEVANT_EXTRAS)
        self.assertEqual(result["skipped_irrelevant"], 1, "無関係記事が skip されていない")
        self.assertEqual(candidates, [], "無関係記事を event 候補に入れてはいけない")

    def test_missing_is_relevant_defaults_to_kept(self):
        """is_relevant 欠落時は従来通り採用扱い（後方互換・安全側）で無関係 skip しない。

        旧モデル/旧 event が is_relevant を返さなくても event 化パスに進めること
        （collect_rss が extras.get('is_relevant', True) を使う契約の locked-in）。
        """
        no_flag = {k: v for k, v in self._IRRELEVANT_EXTRAS.items()
                   if k not in ("is_relevant", "relevance_reason")}
        result, _ = self._run_collect(no_flag)
        self.assertEqual(result["skipped_irrelevant"], 0,
                         "is_relevant 欠落を無関係扱いで skip してはいけない（後方互換）")


if __name__ == "__main__":
    unittest.main()
