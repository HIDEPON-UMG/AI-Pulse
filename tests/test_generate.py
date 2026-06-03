"""SSG（generate_pages）の契約テスト。

検証する不変条件（= ビジネスロジックが変わっても守られるべき意図）:
- L1 entity は 1 件 1 ページのカルテになり、その name がページに現れる（参照→出力の貫通）。
- フィードは掲載閾値 SCORE_MIN を満たすデルタだけを並べ、アーカイブは全デルタを並べる。
- <script> の |tojson アイランドが壊れず feed_count と一致する（autoescape の二重エスケープ無し）。
- 値は autoescape され、HTML へ生のタグが注入されない（XSS 防止）。
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import generate_pages as gp  # noqa: E402
import schema  # noqa: E402


class TestGenerate(unittest.TestCase):
    def setUp(self):
        self.entities, self.events = schema.validate_store(
            gp.DATA_DIR / "entities.jsonl", gp.DATA_DIR / "events.jsonl"
        )

    def test_every_entity_gets_a_karte_with_its_name(self):
        with tempfile.TemporaryDirectory() as d:
            r = gp.generate(Path(d))
            self.assertEqual(r["kartes"], len(self.entities))
            for e in self.entities:
                p = Path(d) / f"karte-{e['entity_id']}.html"
                self.assertTrue(p.exists(), f"karte 欠落: {e['entity_id']}")
                self.assertIn(e["name"], p.read_text(encoding="utf-8"))

    def test_feed_is_thresholded_and_archive_lists_all(self):
        with tempfile.TemporaryDirectory() as d:
            r = gp.generate(Path(d))
            published = [e for e in self.events if e["score"] >= gp.config.SCORE_MIN]
            self.assertEqual(r["feed"], len(published))
            self.assertEqual(r["archive"], len(self.events))
            idx = (Path(d) / "index.html").read_text(encoding="utf-8")
            for e in published:
                self.assertIn(e["headline"], idx)

    def test_ssg_meta_island_is_valid_json(self):
        with tempfile.TemporaryDirectory() as d:
            r = gp.generate(Path(d))
            idx = (Path(d) / "index.html").read_text(encoding="utf-8")
            m = re.search(r'id="ssg-meta">(.*?)</script>', idx, re.S)
            self.assertIsNotNone(m, "ssg-meta アイランドが無い")
            meta = json.loads(m.group(1))  # |tojson が壊れていれば例外
            self.assertEqual(meta["feed_count"], r["feed"])

    def test_autoescape_blocks_html_injection(self):
        ent = {
            "entity_id": "x", "name": "X", "kind": "model", "domain": "language",
            "offering": "oss", "vendor": "V", "category": "model",
            "snapshot_date": "2026-06-02", "positioning": "p",
        }
        ev = {
            "event_id": "e1", "entity_id": "x", "date": "2026-06-02", "category": "model",
            "event_type": "release", "headline": "<script>alert(1)</script>",
            "summary": "s", "score": 90, "importance": "high",
            "source": "src", "source_tier": "T1",
        }
        ctx = gp.build_context([ent], [ev])
        html = gp.make_env().get_template("index.html.j2").render(**ctx, page="feed")
        self.assertNotIn("<script>alert(1)</script>", html)  # 生のタグは出ない
        self.assertIn("&lt;script&gt;", html)               # エスケープされて出る

    def test_list_cell_renders_as_bullets(self):
        """comparison のセル値が配列なら <ul> 箇条書きで描画される。

        なぜ重要か: model レンズは「各社が複数モデルを持ち、強み/コンテキスト長/価格が
        モデルごとに大きく違う」のを 1 セルに列挙する。配列を 1 行テキストに潰すと
        モデル差が読めなくなる回帰を防ぐ（文字列セルは従来どおり 1 行で描く）。
        """
        ent = {
            "entity_id": "x", "name": "X", "kind": "model", "domain": "language",
            "offering": "commercial", "vendor": "V", "category": "model",
            "snapshot_date": "2026-06-02", "positioning": "p",
            "comparison": {"cols": [{"name": "X", "self": True, "cells": {
                "strength": {"v": ["強みA", "強みB"]},
                "context": {"v": ["1M"]},
                "mm_in": {"v": "テキスト・画像", "r": "○"},
                "mm_out": {"v": "テキストのみ", "r": "×"},
                "ecosystem": {"v": "API", "r": "◎"},
                "pricing": {"v": ["$5/$25"]},
            }}]},
        }
        ctx = gp.build_context([ent], [])
        html = gp.make_env().get_template("karte.html.j2").render(
            **ctx, page="karte", k=ctx["kartes"][0])
        self.assertIn('class="cell-list"', html)   # 配列セルは ul 箇条書き
        self.assertIn("強みA", html)
        self.assertIn("強みB", html)
        self.assertIn("テキストのみ", html)        # 文字列セルは従来どおり 1 行

    def test_history_collapses_beyond_five(self):
        """history が5件超なら直近5件を表示し、残りは details に畳む（長大化を防ぐ）。

        なぜ重要か: バージョンを細かく刻むとタイムラインが横/縦に伸びすぎる。
        直近5件をデフォルト表示・残りを折りたたみに固定し、初期表示の情報量を抑える。
        5件以下のときは details を出さない（畳む必要が無いものを畳まない）。
        """
        hist = [{"when": f"2026.{12 - i:02d}", "title": f"v{i}", "now": (i == 0)} for i in range(7)]
        ent = {
            "entity_id": "x", "name": "X", "kind": "model", "domain": "language",
            "offering": "commercial", "vendor": "V", "category": "model",
            "snapshot_date": "2026-06-02", "positioning": "p", "history": hist,
        }
        ctx = gp.build_context([ent], [])
        html = gp.make_env().get_template("karte.html.j2").render(
            **ctx, page="karte", k=ctx["kartes"][0])
        self.assertIn("<details", html)          # 6件目以降は折りたたみに入る
        self.assertIn("さらに 2 件", html)         # 7 - 5 = 2 件が畳まれる
        self.assertIn("v6", html)                # 畳まれた分も DOM には存在（展開で見える）
        # 5件以下なら details を出さない
        ent5 = {**ent, "history": hist[:4]}
        ctx5 = gp.build_context([ent5], [])
        html5 = gp.make_env().get_template("karte.html.j2").render(
            **ctx5, page="karte", k=ctx5["kartes"][0])
        self.assertNotIn("<details", html5)

    def test_feed_source_link_update_badge_and_bullets(self):
        """フィードは本体クリックで出典記事へ飛び・カルテ更新は UPDATE バッジ・要約は箇条書き・
        3指標は判断根拠をツールチップで持つ。source_url が無ければカルテへ戻り要約は1文に戻る。

        なぜ重要か: ユーザーは「ニュースを選んだら出典サイトへ飛びたい / カルテが更新された
        ものを一目で見分けたい / なぜ重要・影響・話題かを根拠で読みたい」。本体リンクがカルテに
        戻る・バッジが出ない・要約が1文のまま・根拠が無い、はいずれも明確な回帰。逆に source_url
        が無いデルタまで出典必須にすると従来導線（カルテ深掘り）が壊れるので、その退避も固定する。
        """
        ent = {
            "entity_id": "x", "name": "X", "kind": "model", "domain": "language",
            "offering": "oss", "vendor": "V", "category": "model",
            "snapshot_date": "2026-06-02", "positioning": "p",
        }
        rich = {
            "event_id": "e1", "entity_id": "x", "date": "2026-06-02", "category": "model",
            "event_type": "release", "headline": "見出し", "summary": "一文要約",
            "score": 90, "importance": "high", "source": "公式", "source_tier": "T1",
            "source_url": "https://example.com/article", "karte_updated": True,
            "summary_points": ["要点1", "要点2", "要点3"],
            "rationale": {"importance": "重要の根拠", "impact": "影響の根拠", "buzz": "話題の根拠"},
        }
        ctx = gp.build_context([ent], [rich])
        html = gp.make_env().get_template("index.html.j2").render(**ctx, page="feed")
        self.assertIn('data-href="https://example.com/article"', html)  # (B) 出典へ飛ぶ
        self.assertIn("UPDATE", html)                                   # (C) 更新バッジ
        self.assertIn('class="summary-points"', html)                   # (D) 箇条書き
        self.assertIn("要点1", html)
        self.assertIn("要点3", html)
        self.assertIn("重要の根拠", html)                                # (D) 判断根拠ツールチップ
        self.assertIn("話題の根拠", html)
        # source_url 無しはカルテへフォールバックし、要約は1文に戻る
        plain = {
            "event_id": "e2", "entity_id": "x", "date": "2026-06-02", "category": "model",
            "event_type": "release", "headline": "見出し2", "summary": "一文要約だけ",
            "score": 90, "importance": "high", "source": "公式", "source_tier": "T1",
        }
        ctx2 = gp.build_context([ent], [plain])
        html2 = gp.make_env().get_template("index.html.j2").render(**ctx2, page="feed")
        self.assertIn('data-href="karte-x.html"', html2)
        self.assertIn("一文要約だけ", html2)
        self.assertNotIn('class="summary-points"', html2)


if __name__ == "__main__":
    unittest.main()
