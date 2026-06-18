"""SSG（generate_pages）の契約テスト。

検証する不変条件（= ビジネスロジックが変わっても守られるべき意図）:
- L1 entity は 1 件 1 ページのカルテになり、その name がページに現れる（参照→出力の貫通）。
- フィードは掲載閾値 SCORE_MIN を満たすデルタだけを並べ、アーカイブは全デルタを並べる。
- <script> の |tojson アイランドが壊れず feed_count と一致する（autoescape の二重エスケープ無し）。
- 値は autoescape され、HTML へ生のタグが注入されない（XSS 防止）。
"""
import html as _html
import datetime as dt
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

    def test_karte_confidence_renders_as_evidence_coverage(self):
        """confidence は「確信度」ではなく、根拠充足の裏取り率として表示する。"""
        ent = {
            "entity_id": "x", "name": "X", "kind": "model", "domain": "language",
            "offering": "oss", "vendor": "V", "category": "model",
            "snapshot_date": "2026-06-08", "positioning": "p",
            "confidence": {"asserted": 2, "speculated": 1, "unverified": 1},
        }
        ev = {
            "event_id": "e1", "entity_id": "x", "date": "2026-06-08", "category": "model",
            "event_type": "release", "headline": "見出し", "summary": "サマリ",
            "score": 90, "importance": "high", "source": "src", "source_tier": "T1",
        }
        ctx = gp.build_context([ent], [ev], build_date=dt.date(2026, 6, 8))
        html = gp.make_env().get_template("karte.html.j2").render(**ctx, k=ctx["kartes"][0])
        self.assertIn("裏取り率 67% ・ 未確認 1件 ・ 予測 1件", html)
        self.assertIn("裏取り率 <span class=\"label\">evidence</span>", html)
        self.assertIn("裏取り済 / VERIFIED", html)
        self.assertNotIn("確信度", html)

    def test_karte_evidence_coverage_excludes_speculated_from_denominator(self):
        """将来予測は裏取り不能な欄なので、裏取り率の分母から外して別件数表示する。"""
        ent = {
            "entity_id": "x", "name": "X", "kind": "model", "domain": "language",
            "offering": "oss", "vendor": "V", "category": "model",
            "snapshot_date": "2026-06-08", "positioning": "p",
            "confidence": {"asserted": 9, "speculated": 99, "unverified": 1},
        }
        ev = {
            "event_id": "e1", "entity_id": "x", "date": "2026-06-08", "category": "model",
            "event_type": "release", "headline": "見出し", "summary": "サマリ",
            "score": 90, "importance": "high", "source": "src", "source_tier": "T1",
        }
        ctx = gp.build_context([ent], [ev], build_date=dt.date(2026, 6, 8))
        self.assertEqual(ctx["kartes"][0]["conf_pct"], 90)
        html = gp.make_env().get_template("karte.html.j2").render(**ctx, k=ctx["kartes"][0])
        self.assertIn("裏取り率 90% ・ 未確認 1件 ・ 予測 99件", html)

    def test_empty_confidence_renders_as_one_unverified_item(self):
        """既存データ未 backfill でも、空の裏取り率を 0 件表示しない。"""
        ent = {
            "entity_id": "x", "name": "X", "kind": "model", "domain": "language",
            "offering": "oss", "vendor": "V", "category": "model",
            "snapshot_date": "2026-06-08", "positioning": "p",
        }
        ev = {
            "event_id": "e1", "entity_id": "x", "date": "2026-06-08", "category": "model",
            "event_type": "release", "headline": "見出し", "summary": "サマリ",
            "score": 90, "importance": "high", "source": "src", "source_tier": "T1",
        }
        ctx = gp.build_context([ent], [ev], build_date=dt.date(2026, 6, 8))
        self.assertEqual(ctx["kartes"][0]["conf_counts"], {"asserted": 0, "speculated": 0, "unverified": 1})

    def test_feed_is_today_only_and_archive_lists_all(self):
        """ユーザー要件 2026-06-04: フィードは最新日付（ref date）の published のみ表示。
        過去分はアーカイブに譲ることでフィードの情報密度を上げる。
        アーカイブは全 events を時系列で並べる（参照整合は守られる）。"""
        with tempfile.TemporaryDirectory() as d:
            r = gp.generate(Path(d))
            published = [e for e in self.events if e["score"] >= gp.config.SCORE_MIN]
            ref_iso = max(e["date"] for e in self.events)
            published_today = [e for e in published if e["date"] == ref_iso]
            self.assertEqual(r["feed"], len(published_today))
            self.assertEqual(r["archive"], len(self.events))
            idx = _html.unescape((Path(d) / "index.html").read_text(encoding="utf-8"))
            for e in published_today:
                self.assertIn(e["headline"], idx)
            # 当日でない published は index に headline が出ない（アーカイブ専有）
            past_published = [e for e in published if e["date"] != ref_iso]
            for e in past_published[:5]:  # 抽出して確認
                self.assertNotIn(e["headline"], idx)

    def test_build_date_uses_generation_day_not_latest_event_day(self):
        ent = {
            "entity_id": "x", "name": "X", "kind": "model", "domain": "language",
            "offering": "oss", "vendor": "V", "category": "model",
            "snapshot_date": "2026-06-07", "positioning": "p",
        }
        ev = {
            "event_id": "e1", "entity_id": "x", "date": "2026-06-07", "category": "model",
            "event_type": "release", "headline": "昨日記事", "summary": "s",
            "score": 90, "importance": "high", "source": "src", "source_tier": "T1",
        }
        ctx = gp.build_context([ent], [ev], build_date=dt.date(2026, 6, 8))
        self.assertEqual(ctx["build"], "2026-06-08")
        self.assertIn("2026-06-08", ctx["ref_date_label"])
        self.assertEqual(ctx["feed_count"], 1)
        self.assertEqual(ctx["feed"][0]["date_rel"], "1日前")

    def test_default_build_date_uses_jst_for_github_actions(self):
        """GitHub Actions の UTC 夜でも、日本時間の更新日を表示する。"""
        class FakeDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return dt.datetime(2026, 6, 16, 22, 33, tzinfo=dt.timezone.utc).astimezone(tz)

        original_datetime = gp.dt.datetime
        try:
            gp.dt.datetime = FakeDateTime
            self.assertEqual(gp._default_build_date(), dt.date(2026, 6, 17))
        finally:
            gp.dt.datetime = original_datetime

    def test_feed_title_uses_summary_point_instead_of_long_translated_headline(self):
        """トップ/カード見出しは長い直訳ではなく、summary_points の要約タイトルを使う。"""
        ent = {
            "entity_id": "x", "name": "X", "kind": "model", "domain": "language",
            "offering": "oss", "vendor": "V", "category": "physical",
            "snapshot_date": "2026-06-08", "positioning": "p",
        }
        long_headline = "ジェンソン・ファンがエロン・マスクについて語ったことは、テスラがスペースXより価値がある理由を示す — 本日はフィジカルAIが主役"
        ev = {
            "event_id": "e1", "entity_id": "x", "date": "2026-06-08", "category": "physical",
            "event_type": "release", "headline": "Very long source headline",
            "headline_ja": long_headline, "summary": "Nvidia CEOはOptimusの市場性を高く評価した。",
            "summary_points": ["Optimusの市場性をNvidia CEOが高評価", "Teslaは2027年販売を目指す", "物理AI市場の拡大が焦点"],
            "score": 90, "importance": "high", "source": "src", "source_tier": "T1",
        }
        ctx = gp.build_context([ent], [ev], build_date=dt.date(2026, 6, 8))
        self.assertEqual(ctx["feed"][0]["display_headline"], "Optimusの市場性をNvidia CEOが高評価")
        html = gp.make_env().get_template("index.html.j2").render(**ctx, page="feed")
        self.assertIn("<h2 title=\"Very long source headline\">Optimusの市場性をNvidia CEOが高評価</h2>", html)
        self.assertIn('data-digest-title="Optimusの市場性をNvidia CEOが高評価"', html)

    def test_karte_index_page_is_built_with_category_groups(self):
        """カルテ一覧ページ（karte-index.html）が出力され、全カルテ名がカテゴリ別カードで載る。"""
        with tempfile.TemporaryDirectory() as d:
            gp.generate(Path(d))
            ki_path = Path(d) / "karte-index.html"
            self.assertTrue(ki_path.exists(), "カルテ一覧ページが生成されていない")
            html = ki_path.read_text(encoding="utf-8")
            for e in self.entities:
                self.assertIn(e["name"], html, f"カルテ名 {e['name']!r} がカルテ一覧に出ない")
            self.assertIn("ki-card", html)
            self.assertIn("ki-group", html)
            self.assertIn('class="dateline"><span class="live-dot"></span>', html)
            self.assertIn("カルテ一覧 / KARTE INDEX", html)

    def test_repo_radar_page_is_built_and_anonymized(self):
        """Repo Radar ページは公開 JSONL だけを描画し、IdeaStash の具体情報を出さない。"""
        row = {
            "date": "2026-06-13",
            "repo": "acme/useful-repo",
            "repo_url": "https://github.com/acme/useful-repo",
            "name": "useful-repo",
            "description": "Useful repo",
            "homepage": "",
            "language": "Python",
            "license": "MIT",
            "topics": ["ai"],
            "stars": 100,
            "forks": 5,
            "open_issues": 1,
            "created_at": "2026-06-01T00:00:00Z",
            "pushed_at": "2026-06-13T00:00:00Z",
            "thumbnail_url": "https://opengraph.githubassets.com/ai-pulse/acme/useful-repo",
            "latest_release": None,
            "signals": [{"source": "hn", "title": "Show HN: Useful repo", "url": "https://news.ycombinator.com/item?id=1"}],
            "score": 88,
            "summary": "AI 開発の補助ツールです。",
            "feature_outline": [
                {"lens": "Capability", "text": "LLM ワークフローの調査を補助する"},
                {"lens": "Activation", "text": "既存 Python 環境に追加しやすい"},
            ],
            "developer_use_case": "実装前調査に使えます。",
            "implementation_difficulty": "easy: Python だけで試せます。",
            "pricing_or_license": "MIT",
            "adoption_reason": "運用適合性: AI-Pulse の収集基盤へ小さく試せるため採用候補にする。",
            "ai_pulse_fit": ["収集基盤"],
            "ideastash_fit_public": ["UI/UX 改善"],
            "risk_notes": ["保守状況を確認してください"],
            "status": "evaluated",
        }
        original = gp.collect_repo_radar.load_public_rows
        gp.collect_repo_radar.load_public_rows = lambda: [row]
        try:
            with tempfile.TemporaryDirectory() as d:
                r = gp.generate(Path(d))
                self.assertIn("repo-radar.html", r["pages"])
                html = (Path(d) / "repo-radar.html").read_text(encoding="utf-8")
        finally:
            gp.collect_repo_radar.load_public_rows = original
        self.assertIn("acme/useful-repo", html)
        self.assertIn("リポジトリ一覧 / REPOSITORY LIST", html)
        self.assertIn("AI駆動開発に資するGithub Repository</h1>", html)
        self.assertNotIn("<mark>Github Repository", html)
        self.assertIn('class="dateline"><span class="live-dot"></span>', html)
        self.assertIn('<main class="app-main">', html)
        self.assertRegex(html, r'<main class="app-main">\s*<div class="wrap">\s*<section class="rr-head">')
        self.assertIn("UI/UX 改善", html)
        self.assertIn("Show HN: Useful repo", html)
        self.assertIn("news.ycombinator.com/item?id=1", html)
        self.assertIn("repo-card", html)
        self.assertIn("repo-aside", html)
        self.assertIn('class="embed" data-src="hn"', html)
        self.assertIn("Adoption Lens", html)
        self.assertIn("WHAT IT DOES", html)
        self.assertIn("WHERE IT FITS", html)
        self.assertIn("WHAT TO WATCH", html)
        self.assertIn("WHY FOR US", html)
        self.assertIn("opsfit", html)
        self.assertIn('class="body-list em-body"', html)
        self.assertIn('class="body-list axis-list"', html)
        self.assertIn('class="body-list reason"', html)
        self.assertIn("<mark>AI</mark> 開発", html)
        self.assertIn("<b>運用適合性</b>", html)
        self.assertIn("保守状況を<u>確認</u>してください", html)
        self.assertIn('data-level="低"', html)
        self.assertIn("リポジトリを開く", html)
        self.assertIn("運用適合性", html)
        self.assertIn("2026-06-01", html)
        self.assertIn("2026-06-13", html)
        self.assertIn("★ 100", html)
        self.assertIn("class=\"og\"", html)
        self.assertIn("opengraph.githubassets.com/ai-pulse/acme/useful-repo", html)
        self.assertNotIn("SecretTask-mobile-copy-2026-06-01.md", html)
        self.assertNotIn("スマホのコピーボタン修正", html)
        self.assertNotIn(r"C:\Users\hidek\Obsidian", html)

    def test_main_nav_labels_are_english_with_repositories_after_karte(self):
        """メニューバーは英語表記にし、Repositories は Karte の右側に置く。

        なぜ重要か: BuzzPost 追加後のメニューバーは UI トーンとして英語に統一する。
        """
        with tempfile.TemporaryDirectory() as d:
            gp.generate(Path(d))
            html = (Path(d) / "repo-radar.html").read_text(encoding="utf-8")

        for label in (">Feed</a>", ">Archive</a>", ">Karte</a>", ">Repositories</a>", ">BuzzPost</a>"):
            self.assertIn(label, html)
        self.assertLess(html.index(">Karte</a>"), html.index(">Repositories</a>"))
        self.assertNotIn(">フィード</a>", html)
        self.assertNotIn(">アーカイブ</a>", html)
        self.assertNotIn(">カルテ</a>", html)
        self.assertNotIn(">リポジトリ</a>", html)
        self.assertNotIn(">Repo Radar</a>", html)

    def test_buzzpost_page_is_built_from_public_rows(self):
        """BuzzPost ページは公開 JSONL だけを描画し、X 投稿をカテゴリ別に読める。"""
        original_post = "Claude Code agents are everywhere today.\n\nhttps://x.com/example/status/111"
        row = {
            "date": "2026-06-18",
            "category": "model",
            "category_label": "モデル/LLM",
            "glyph": "◆",
            "source": "x-rss:buzzpost-model",
            "source_query": "(GPT-5 OR Claude OR Gemini) lang:en",
            "post_url": "https://x.com/example/status/111",
            "title": "Generated title must not be shown",
            "text": original_post,
            "published_at": "2026-06-17T23:10:00+00:00",
            "buzz_score": 156,
            "absolute_score": 120,
            "velocity_score": 36.2,
        }
        original = gp.collect_buzz_posts.load_public_rows
        gp.collect_buzz_posts.load_public_rows = lambda: [row]
        try:
            with tempfile.TemporaryDirectory() as d:
                r = gp.generate(Path(d))
                self.assertIn("buzz-posts.html", r["pages"])
                html = (Path(d) / "buzz-posts.html").read_text(encoding="utf-8")
        finally:
            gp.collect_buzz_posts.load_public_rows = original
        self.assertIn("BuzzPost", html)
        self.assertIn("Claude Code agents are everywhere", html)
        self.assertIn(original_post, html)
        self.assertIn('class="x-embed-shell"', html)
        self.assertIn('class="buzz-side-rail"', html)
        self.assertLess(html.index('class="buzz-side-rail"'), html.index('class="x-embed-card"'))
        self.assertIn('<blockquote class="twitter-tweet"', html)
        self.assertIn('data-theme="dark"', html)
        self.assertIn("platform.twitter.com/widgets.js", html)
        self.assertNotIn('class="x-post-card"', html)
        self.assertNotIn('class="buzz-meta-rail"', html)
        self.assertIn("abs 120", html)
        self.assertIn("vel 36.2/h", html)
        self.assertNotIn("Generated title must not be shown", html)
        self.assertNotIn("<h2><a", html)
        self.assertIn("https://x.com/example/status/111", html)
        self.assertIn("モデル/LLM", html)
        self.assertIn("BUZZ SCORE", html)
        self.assertIn('data-page="buzzpost"', html)

    def test_buzzpost_empty_page_explains_threshold_drops(self):
        """0件時でも、収集未実行なのか閾値除外なのかを画面から判断できる。"""
        original_rows = gp.collect_buzz_posts.load_public_rows
        original_stats = gp.collect_buzz_posts.load_stats
        gp.collect_buzz_posts.load_public_rows = lambda: []
        gp.collect_buzz_posts.load_stats = lambda: {
            "latest": "2026-06-18",
            "candidate_count": 12,
            "collected": 0,
            "dropped_threshold": 12,
            "dropped_duplicate": 0,
            "degraded": 0,
            "min_absolute_score": 25,
            "min_velocity_score": 8.0,
        }
        try:
            with tempfile.TemporaryDirectory() as d:
                gp.generate(Path(d))
                html = (Path(d) / "buzz-posts.html").read_text(encoding="utf-8")
        finally:
            gp.collect_buzz_posts.load_public_rows = original_rows
            gp.collect_buzz_posts.load_stats = original_stats

        self.assertIn("<span>候補</span><b>12</b><small>件</small>", html)
        self.assertIn("<span>閾値未満</span><b>12</b><small>件</small>", html)
        self.assertIn("absolute_score ≥ 25", html)
        self.assertIn("velocity_score ≥ 8.0/h", html)
        self.assertIn("収集は成功しています", html)

    def test_karte_index_has_feed_and_karte_update_badges(self):
        """ユーザー要件 2026-06-04:「何が更新されたか」を一目で示すため、
        カルテ一覧の各カードは『📰 フィード』(events 最新) と『📋 カルテ』(entity.snapshot_date)
        の 2 バッジを並列で持つ。snapshot_date は ENTITY_REQUIRED なので必ず出る。"""
        with tempfile.TemporaryDirectory() as d:
            gp.generate(Path(d))
            html = (Path(d) / "karte-index.html").read_text(encoding="utf-8")
            # ラッパと両バッジ class が描画される
            self.assertIn("upd-row", html)
            self.assertIn("upd feed", html)
            self.assertIn("upd karte", html)
            # 接頭辞ラベル (HTML エンティティ化されても本体絵文字は素のまま autoescape 対象外)
            self.assertIn("📰 フィード", html)
            self.assertIn("📋 カルテ", html)
            # 全 entity に snapshot_date があるので、karte バッジは少なくとも全件分は描画される
            self.assertGreaterEqual(html.count('class="upd karte'), len(self.entities))

    def test_related_entities_render_as_karte_chips(self):
        """related_entities が指定された event は、主+関連の実カルテ名がフィード/アーカイブで chip 描画される。"""
        ent_main = {
            "entity_id": "main", "name": "MainKarte", "kind": "model", "domain": "language",
            "offering": "oss", "vendor": "V", "category": "model",
            "snapshot_date": "2026-06-04", "positioning": "p",
        }
        ent_rel = {
            "entity_id": "rel", "name": "RelKarte", "kind": "model", "domain": "language",
            "offering": "oss", "vendor": "W", "category": "model",
            "snapshot_date": "2026-06-04", "positioning": "p2",
        }
        ev = {
            "event_id": "e1", "entity_id": "main", "date": "2026-06-04", "category": "model",
            "event_type": "release", "headline": "見出し", "summary": "サマリ",
            "score": 90, "importance": "high", "source": "src", "source_tier": "T1",
            "related_entities": ["rel"],
        }
        ctx = gp.build_context([ent_main, ent_rel], [ev])
        idx_html = gp.make_env().get_template("index.html.j2").render(**ctx, page="feed")
        arc_html = gp.make_env().get_template("archive.html.j2").render(**ctx, page="archive")
        # フィードに主+関連の両方が chip で出る
        self.assertIn("MainKarte", idx_html)
        self.assertIn("RelKarte", idx_html)
        self.assertIn("karte-chip", idx_html)
        # アーカイブにも主+関連の両方が chip で出る
        self.assertIn("MainKarte", arc_html)
        self.assertIn("RelKarte", arc_html)

    def test_karte_chip_font_shrinks_to_fit_thumb_column(self):
        """サムネ列 200px に長文カルテ名 chip が収まるよう font_size を自動縮小する。

        なぜ重要か: 2026-06-05 ユーザー報告で "Physical Intelligence" (21 字 ASCII) chip が
        サムネ画像の右端を超え SUMMARY 領域に被った。境界 1 関数 `_karte_fit_metrics` で
        chip 全幅を逆算し base 22→13px 程度に縮小、テンプレが inline style で出力する設計を
        ([feedback_check_design_principles] §2 境界 1 箇所集約)、ここで locked-in する。
        """
        # 長文 ASCII (21字 "Physical Intelligence") は base 22 から縮小される
        m_long = gp._karte_fit_metrics("Physical Intelligence")
        self.assertLess(m_long["font_size"], 22, "長文 chip が縮小されていない")
        self.assertGreaterEqual(m_long["font_size"], 11, "下限 11px を割っている")
        # padding も font_size に比例
        self.assertLessEqual(m_long["px"], 17)
        # 短文 ASCII (6字 "OpenAI") は base 22 を維持
        m_short = gp._karte_fit_metrics("OpenAI")
        self.assertEqual(m_short["font_size"], 22)
        # 空文字でも例外を出さない
        m_empty = gp._karte_fit_metrics("")
        self.assertEqual(m_empty["font_size"], 22)
        # index.html の chip に inline style (font-size, padding) が出力される
        ent = {
            "entity_id": "physical-intelligence", "name": "Physical Intelligence",
            "kind": "model", "domain": "robotics", "offering": "commercial",
            "vendor": "PI", "category": "physical",
            "snapshot_date": "2026-06-04", "positioning": "p",
        }
        ev = {
            "event_id": "e1", "entity_id": "physical-intelligence",
            "date": "2026-06-04", "category": "physical",
            "event_type": "release", "headline": "test", "summary": "s",
            "score": 90, "importance": "high", "source": "src", "source_tier": "T1",
        }
        ctx = gp.build_context([ent], [ev])
        idx_html = gp.make_env().get_template("index.html.j2").render(**ctx, page="feed")
        self.assertIn('class="karte-chip" style="font-size:', idx_html)
        # 縮小値 (< 22) が style に書かれている
        self.assertRegex(idx_html, r'karte-chip" style="font-size:1\dpx;padding:\d+px \d+px"')

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

    def test_sub_history_renders_collapsed_by_default(self):
        """サブ・ヒストリーは初期状態で畳み、サブモデル単位の行で描画する。

        なぜ重要か: 三大モデルのカルテでは、主表示はフロンティアモデルの系譜に限定する。
        廉価/高速/派生モデルまで常時表示すると履歴の焦点がぼやけるため、展開操作でだけ読める
        `details.sub-history` として固定する。
        """
        ent = {
            "entity_id": "x", "name": "X", "kind": "model", "domain": "language",
            "offering": "commercial", "vendor": "V", "category": "model",
            "snapshot_date": "2026-06-02", "positioning": "p",
            "history": [{"when": "2026.05", "title": "Frontier", "now": True}],
            "sub_history": [{
                "model": "X mini",
                "items": [{"when": "2026.04", "title": "mini 更新", "note": "高速版"}],
            }],
        }
        ctx = gp.build_context([ent], [])
        html = gp.make_env().get_template("karte.html.j2").render(
            **ctx, page="karte", k=ctx["kartes"][0])
        self.assertIn('<details class="sub-history">', html)
        self.assertNotIn('<details class="sub-history" open>', html)
        self.assertIn("サブ・ヒストリー", html)
        self.assertIn("X mini", html)
        self.assertIn("mini 更新", html)

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
            "rationale": {
                "importance": "主力モデルのメジャー更新で文脈処理・価格すべてに関わる基盤アップデートのため重要度を高と判定。",
                "impact": "下流のコーディングツールが採用モデルを更新する波及があるため影響度を高と判定。",
                "buzz": "Anthropic 公式発表でニュース性スコア90。注目が大きいため話題性を高と判定。"},
        }
        ctx = gp.build_context([ent], [rich])
        html = gp.make_env().get_template("index.html.j2").render(**ctx, page="feed")
        self.assertIn('data-href="https://example.com/article"', html)  # (B) 出典へ飛ぶ
        self.assertIn("UPDATE", html)                                   # (C) 更新バッジ
        self.assertIn('class="summary-points"', html)                   # (D) 箇条書き
        self.assertIn("要点1", html)
        self.assertIn("要点3", html)
        self.assertIn("重要度を高と判定", html)                          # (D) 判断根拠ツールチップ (Part 7 で 20+ 字必須化)
        self.assertIn("話題性を高と判定", html)
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


    def test_karte_feed_items_include_main_and_related_events(self):
        """カルテ最下段「関連ニュース」は、主 entity_id 一致 + related_entities に含まれる
        events を **新しい順で全件** 入れる（SCORE_MIN フィルタは外す = カルテはアーカイブ的役割）。

        なぜ重要か: 「このカルテに紐づくニュース」を1ページで網羅できることがカルテの価値。
        SCORE_MIN で間引くと、過去の小ネタが消えて履歴が読めなくなる回帰になる。
        related_entities も拾わないと「複数カルテに同時影響」した events が片側にしか出ない。
        """
        ent_main = {
            "entity_id": "main", "name": "MainKarte", "kind": "model", "domain": "language",
            "offering": "oss", "vendor": "V", "category": "model",
            "snapshot_date": "2026-06-04", "positioning": "p",
        }
        ent_rel = {
            "entity_id": "rel", "name": "RelKarte", "kind": "model", "domain": "language",
            "offering": "oss", "vendor": "W", "category": "model",
            "snapshot_date": "2026-06-04", "positioning": "p2",
        }
        ent_other = {
            "entity_id": "other", "name": "Other", "kind": "model", "domain": "language",
            "offering": "oss", "vendor": "X", "category": "model",
            "snapshot_date": "2026-06-04", "positioning": "p3",
        }
        # main 直接（高 score）/ main 直接（低 score、SCORE_MIN 以下のはず）/ rel に main を related で含む / 無関係
        ev_main_hi = {
            "event_id": "m1", "entity_id": "main", "date": "2026-06-04", "category": "model",
            "event_type": "release", "headline": "Main 高スコア", "summary": "s",
            "score": 95, "importance": "high", "source": "src", "source_tier": "T1",
        }
        ev_main_lo = {
            "event_id": "m2", "entity_id": "main", "date": "2026-06-03", "category": "model",
            "event_type": "release", "headline": "Main 低スコア", "summary": "s",
            "score": 1, "importance": "low", "source": "src", "source_tier": "T3",
        }
        ev_rel_with_main = {
            "event_id": "r1", "entity_id": "rel", "date": "2026-06-02", "category": "model",
            "event_type": "release", "headline": "Rel から main 参照", "summary": "s",
            "score": 70, "importance": "mid", "source": "src", "source_tier": "T2",
            "related_entities": ["main"],
        }
        ev_other = {
            "event_id": "o1", "entity_id": "other", "date": "2026-06-01", "category": "model",
            "event_type": "release", "headline": "無関係", "summary": "s",
            "score": 80, "importance": "mid", "source": "src", "source_tier": "T2",
        }
        ctx = gp.build_context(
            [ent_main, ent_rel, ent_other],
            [ev_main_hi, ev_main_lo, ev_rel_with_main, ev_other],
        )
        kartes_by_id = {k["id"]: k for k in ctx["kartes"]}
        main_feed = kartes_by_id["main"]["feed_items"]
        ids = [s["id"] for s in main_feed]
        # 主 entity_id 一致 (m1, m2) + related_entities 一致 (r1) の 3 件、無関係 o1 は入らない
        self.assertEqual(set(ids), {"m1", "m2", "r1"})
        # SCORE_MIN フィルタは外す = 低スコア m2 も入る
        self.assertIn("m2", ids)
        # 新しい順 (date desc): m1 (06-04) → m2 (06-03) → r1 (06-02)
        self.assertEqual(ids, ["m1", "m2", "r1"])
        # 無関係 other カルテには影響しない
        other_ids = [s["id"] for s in kartes_by_id["other"]["feed_items"]]
        self.assertEqual(other_ids, ["o1"])
        # テンプレでも .karte-feed セクションに描画される
        html = gp.make_env().get_template("karte.html.j2").render(
            **ctx, page="karte", k=kartes_by_id["main"])
        self.assertIn("karte-feed", html)
        self.assertIn("Main 高スコア", html)
        self.assertIn("Main 低スコア", html)
        self.assertIn("Rel から main 参照", html)
        self.assertNotIn("無関係", html)


    def test_existing_events_use_diverse_emphasis(self):
        """既存 events.jsonl の各 event は 3 種強調記法（**太字** / ==マーカー== / __下線__）
        を使い分けて意味分け表示できる状態にある（プロンプト絶対条件 1 / 2 の集計版）。

        なぜ重要か: rewrite_emphasis でデータ全体に意味分けを当てた後、回帰で「太字一色」状態に
        戻らないように下限を locked-in する。Gemini ゲート（llm_gemini._check_shape）と二段構え。
        - 強調記法ゼロの event は 0 件（プロンプト絶対条件 2）。
        - 太字以外（==/__）を 1 つ以上使う event の比率が 40% 以上（rewrite 直後で 58%、
          将来の追加が単一カテゴリに偏っても 40% 下限を割らない設計）。
        """
        import re
        RE_ANY = re.compile(r"\*\*[^*\n]+\*\*|==[^=\n]+==|__[^_\n]+__")
        RE_DIVERSE = re.compile(r"==[^=\n]+==|__[^_\n]+__")
        no_emph = []
        diverse_count = 0
        for e in self.events:
            text = (e.get("summary") or "") + "\n" + "\n".join(e.get("summary_points") or [])
            if not RE_ANY.search(text):
                no_emph.append(e["event_id"])
            if RE_DIVERSE.search(text):
                diverse_count += 1
        self.assertEqual(no_emph, [], f"強調記法ゼロの event: {no_emph}")
        ratio = diverse_count / len(self.events)
        self.assertGreaterEqual(
            ratio, 0.40,
            f"==/__ を使う event が {diverse_count}/{len(self.events)} ({ratio:.0%}) "
            f"= 40% 未満。プロンプト絶対条件 1（太字だけ禁止）が守られていない可能性"
        )


if __name__ == "__main__":
    unittest.main()
