"""ブランド面の不変条件契約テスト（2026-06-05 追加）。

ユーザー要件 3 件を class of bugs として 1 ファイルで locked-in する
（[[feedback_check_design_principles]] §4 契約テスト 1 件で構造的に封じる）:

1. **テーマ切替 UI 廃止の不可逆化**
   2026-06-05 にユーザー指示で `palette-switch` 配色切替を廃止した。
   将来の `_header.html.j2` / `theme.css` の "片手落ち" 改修で UI が
   復活したり data-palette セレクタが残ったりするのを物理的に検出する。

2. **OGP / Twitter Card の絶対 URL 保証**
   `og:image` / `twitter:image` は CDN/SNS で相対パスでは解決されない。
   `_head.html.j2` で `site_url` を組立に使い、ビルド成果 site/*.html が
   `https://hidepon-umg.github.io/AI-Pulse/og-image.png` を持つことを
   1 件で固定する。テンプレ単独編集で http(s) スキームが落ちる回帰を防ぐ。

3. **OGP 画像アセットの site/ コピー貫通**
   tools/gen_og_image.py が生成した `static/og-image.png` が
   `_copy_assets` で `site/og-image.png` に必ず流れる（拡張子は
   既存 ASSET_SUFFIXES に含まれている）。og:image の指す URL が
   404 にならないことを保証する。
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import generate_pages as gp  # noqa: E402


class TestBrandingInvariants(unittest.TestCase):

    # ---- (1) テーマ切替 UI 不在 ----

    def test_header_template_has_no_palette_switch_markup(self):
        """配色切替 UI を構成する DOM/属性が _header.html.j2 に存在しないこと。
        部品名 (palette-switch / sw-cyan / sw-azure / sw-ion / data-palette / aipulse-palette)
        を全て禁止語として grep し、1 つでも残れば失敗。"""
        src = (ROOT / "templates" / "_header.html.j2").read_text(encoding="utf-8")
        banned = ["palette-switch", "sw-cyan", "sw-azure", "sw-ion",
                  "data-palette", "aipulse-palette"]
        for b in banned:
            self.assertNotIn(
                b, src,
                f"_header.html.j2 に削除済みの配色切替 UI 部品 {b!r} が残存している",
            )

    def test_theme_css_has_no_palette_selectors_or_swatches(self):
        """`[data-palette="..."]` セレクタと `.palette-switch` / `.sw-*` CSS が
        theme.css に存在しないこと（コメント内の歴史記述は許容するため、
        セレクタ表記そのものを正規表現で検出する）。"""
        src = (ROOT / "static" / "theme.css").read_text(encoding="utf-8")
        self.assertNotRegex(
            src, r"\[data-palette\s*=",
            "theme.css に `[data-palette=...]` セレクタが残存",
        )
        # CSS ルール本体（`{` を伴う宣言行）として `.palette-switch` / `.sw-*` が
        # 復活していないかを検出。コメントの歴史記述（`/* palette */`）は許容する。
        self.assertNotRegex(
            src, r"\.palette-switch\s*[{.\s]",
            "theme.css に `.palette-switch` CSS ルールが残存",
        )
        self.assertNotRegex(
            src, r"\.sw-(cyan|azure|ion)\b",
            "theme.css に `.sw-cyan/azure/ion` の swatch CSS が残存",
        )

    def test_app_js_has_no_palette_persistence(self):
        """app.js から palette 永続化ロジック（applyPalette / initPalette /
        aipulse-palette localStorage キー）が削除されていること。"""
        src = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        for b in ["applyPalette", "initPalette", "aipulse-palette"]:
            self.assertNotIn(b, src, f"app.js に削除済み palette 関連識別子 {b!r} が残存")

    # ---- (2) OGP 絶対 URL ----

    def test_built_pages_emit_absolute_og_image_url(self):
        """ビルド成果の index / archive / 任意 karte に `og:image` が出力され、
        値が SITE_URL を先頭に持つ絶対 URL である（`/` や相対 `og-image.png` は不可）。"""
        with tempfile.TemporaryDirectory() as d:
            gp.generate(Path(d))
            site_url = gp.config.SITE_URL
            self.assertTrue(
                site_url.startswith("https://") and site_url.endswith("/"),
                f"SITE_URL は https:// で始まり / で終わる必要がある: {site_url!r}",
            )
            expected = f"{site_url}og-image.png"
            for name in ("index.html", "archive.html", "karte-index.html"):
                html = (Path(d) / name).read_text(encoding="utf-8")
                # og:image の絶対 URL
                m = re.search(
                    r'<meta\s+property="og:image"\s+content="([^"]+)"',
                    html,
                )
                self.assertIsNotNone(m, f"{name} に og:image meta が無い")
                self.assertEqual(
                    m.group(1), expected,
                    f"{name} の og:image が SITE_URL ベースの絶対 URL でない",
                )
                # twitter:image も同様（Twitter Card 用）
                m2 = re.search(
                    r'<meta\s+name="twitter:image"\s+content="([^"]+)"',
                    html,
                )
                self.assertIsNotNone(m2, f"{name} に twitter:image meta が無い")
                self.assertEqual(m2.group(1), expected)
                # twitter:card は summary_large_image（1200x630 の正式値）
                self.assertIn('name="twitter:card" content="summary_large_image"', html)

    # ---- (4) モバイル横スワイプによる主要 3 ページ間遷移 ----

    def test_built_pages_emit_data_page_attribute(self):
        """ユーザー要件 2026-06-05: スマホで横スワイプして feed/archive/karte 間を遷移したい。
        app.js の initSwipeNav は body.dataset.page を見て遷移先を決めるため、
        4 ページ種別すべてで <body data-page="..."> が必ず出力される設計を locked-in する。
        テンプレ片手落ち (新規ページで data-page を入れ忘れ) を CI で防ぐ。"""
        with tempfile.TemporaryDirectory() as d:
            gp.generate(Path(d))
            cases = {
                "index.html": "feed",
                "archive.html": "archive",
                "karte-index.html": "karte_index",
            }
            for name, expected in cases.items():
                html = (Path(d) / name).read_text(encoding="utf-8")
                self.assertRegex(
                    html, rf'<body[^>]*data-page="{expected}"',
                    f"{name} の <body> に data-page=\"{expected}\" が無い",
                )
            # 個別カルテも必ず data-page="karte" を持つ（initSwipeNav は早期 return）
            karte_html = (Path(d) / "karte-claude-opus.html").read_text(encoding="utf-8")
            self.assertRegex(
                karte_html, r'<body[^>]*data-page="karte"',
                "個別カルテ <body> に data-page=\"karte\" が無い",
            )

    def test_app_js_implements_swipe_nav_with_locked_order(self):
        """app.js の initSwipeNav 不変条件を locked-in する。

        ナビ順序 feed → archive → karte_index は UI ヘッダの並びと一致させており、
        将来 boot() から initSwipeNav を外したり、ORDER 配列の並び/値が変わると
        スマホ操作の方向感覚が壊れる。これを 1 件で物理検出する。
        """
        src = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        # boot から呼ばれていること
        self.assertRegex(
            src, r"function\s+boot\s*\(\s*\)\s*\{[^}]*initSwipeNav\s*\(\s*\)",
            "boot() から initSwipeNav() が呼ばれていない",
        )
        # ORDER 配列の中身と順序を厳密照合
        m = re.search(r"var\s+ORDER\s*=\s*\[([^\]]+)\]", src)
        self.assertIsNotNone(m, "ORDER 配列が見つからない")
        order = re.findall(r'"([^"]+)"', m.group(1))
        self.assertEqual(
            order, ["feed", "archive", "karte_index"],
            f"swipe ナビ順序 (feed → archive → karte_index) が崩れている: {order}",
        )
        # 個別カルテ (data-page="karte") は ORDER に含まれない設計を locked-in
        self.assertNotIn(
            "karte", order,
            "個別カルテ (data-page=karte) が ORDER 配列に混入している",
        )
        # 縦スクロール優先 (passive: true / Y_TOLERANCE) が抜けていない
        self.assertIn("passive: true", src,
                      "touch listener が passive で登録されていない (縦スクロール阻害)")
        self.assertRegex(
            src, r"clientWidth\s*>=\s*769",
            "desktop (>=769px) 除外ガードが無く、PC でも誤動作しうる",
        )

    # ---- (5) View Transitions による wipe 遷移 ----

    def test_theme_css_enables_cross_document_view_transitions(self):
        """ユーザー要件 2026-06-05: ページ遷移にワイプエフェクトを当てたい。
        theme.css の @view-transition / ::view-transition-* が
        cross-document モードで設定されていることを locked-in する。

        なぜ重要か: View Transitions API は CSS だけで宣言的に動くため、
        将来 minify ツール等が `@view-transition` ルールを atrule 不明として
        丸ごと落とす回帰や、`navigation: auto` を `none` に書き換える誤改修を
        構造的に検出する。1 ファイル 1 ルールで class of bugs を封じる。
        """
        src = (ROOT / "static" / "theme.css").read_text(encoding="utf-8")
        # cross-document モード (navigation: auto) が宣言されている
        self.assertRegex(
            src, r"@view-transition\s*\{\s*navigation\s*:\s*auto",
            "@view-transition { navigation: auto } が theme.css に無い",
        )
        # 古いページ・新しいページ両方のアニメ宣言があること
        self.assertRegex(
            src, r"::view-transition-old\(root\)\s*\{[^}]*animation\s*:",
            "::view-transition-old(root) の animation が無い",
        )
        self.assertRegex(
            src, r"::view-transition-new\(root\)\s*\{[^}]*animation\s*:",
            "::view-transition-new(root) の animation が無い",
        )
        # wipe (clip-path) 系の keyframes が定義されている
        self.assertRegex(
            src, r"@keyframes\s+wipe-out-to-right\b",
            "wipe-out-to-right keyframes が無い",
        )
        self.assertRegex(
            src, r"@keyframes\s+wipe-in-from-left\b",
            "wipe-in-from-left keyframes が無い",
        )
        # アクセシビリティ: prefers-reduced-motion で短縮する分岐がある
        self.assertRegex(
            src,
            r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)[^}]*\{[^{]*::view-transition",
            "prefers-reduced-motion で View Transitions を短縮する分岐が無い",
        )

    # ---- (6) OGP 画像アセットが site/ にコピーされる ----

    def test_og_image_asset_exists_and_is_copied(self):
        """`static/og-image.png` が存在し、`_copy_assets` で site/ に流れる。
        png 拡張子は ASSET_SUFFIXES に含まれており、新規拡張子追加の片手落ちで
        漏れる回帰を 1 件で固定する。"""
        src = ROOT / "static" / "og-image.png"
        self.assertTrue(
            src.exists(),
            "static/og-image.png が無い。tools/gen_og_image.py を実行して生成すること",
        )
        # 拡張子が ASSET_SUFFIXES に含まれることをホワイトリスト型で確認
        self.assertIn(".png", gp.ASSET_SUFFIXES)
        with tempfile.TemporaryDirectory() as d:
            gp.generate(Path(d))
            dst = Path(d) / "og-image.png"
            self.assertTrue(dst.exists(), "site/og-image.png にコピーされていない")
            # コピー先サイズが空でないこと（バイナリ破損や 0-byte 事故の検出）
            self.assertGreater(dst.stat().st_size, 1000,
                               "コピー先 og-image.png のサイズが極端に小さい")


if __name__ == "__main__":
    unittest.main()
