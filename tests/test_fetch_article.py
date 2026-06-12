"""契約テスト: fetch_article.resolve / extract の不変条件 2 件。

なぜ重要か（意図）:
  Google News redirect URL（urllib では publisher に解決不可）と短文ページ（paywall/404）の
  2 種類が ingest に漏れると、UI の source link が news.google.com のままになったり、空白本文を
  Gemini に投げてしまったりする。境界で 2 件 locked-in する。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import config  # noqa: E402
import fetch_article  # noqa: E402


class TestFetchArticleContract(unittest.TestCase):
    def test_redirect_resolves_to_publisher(self):
        """gnewsdecoder が成功したら publisher URL を返す。失敗したら ArticleFetchError。"""
        gnews_url = "https://news.google.com/rss/articles/CBMicHR0cHM6Ly93d3cuemRuZXQuY29tL2FydGljbGUv"

        # 成功ケース: 解決済み URL を返す
        with patch.object(fetch_article, "gnewsdecoder",
                          return_value={"status": True, "decoded_url": "https://www.zdnet.com/article/x/"}):
            url = fetch_article.resolve(gnews_url)
        self.assertEqual(url, "https://www.zdnet.com/article/x/")

        # 失敗ケース: status=False は ArticleFetchError
        with patch.object(fetch_article, "gnewsdecoder",
                          return_value={"status": False, "message": "decode failed"}):
            with self.assertRaises(fetch_article.ArticleFetchError):
                fetch_article.resolve(gnews_url)

        # gnewsdecoder が例外を投げても ArticleFetchError に変換される
        with patch.object(fetch_article, "gnewsdecoder",
                          side_effect=RuntimeError("internal")):
            with self.assertRaises(fetch_article.ArticleFetchError):
                fetch_article.resolve(gnews_url)

        # 既に publisher URL (news.google.com 以外) はそのまま返す
        passthrough = "https://www.example.com/article/x"
        self.assertEqual(fetch_article.resolve(passthrough), passthrough)

    def test_short_body_drops(self):
        """trafilatura が短文を返したら ArticleFetchError でドロップ（paywall/404 を本文として食わない）。"""
        gnews_url = "https://news.google.com/rss/articles/SHORT_BODY_CASE"
        publisher = "https://www.zdnet.com/article/x/"
        with patch.object(fetch_article, "gnewsdecoder",
                          return_value={"status": True, "decoded_url": publisher}):
            # trafilatura.fetch_url が空応答を返すケース
            with patch.object(fetch_article.trafilatura, "fetch_url", return_value=""):
                with patch.object(fetch_article.fetch_escalation, "fetch_with_escalation",
                                  return_value=fetch_article.fetch_escalation.FetchResult(
                                      url=publisher, stage="fetcher", ok=False, error="empty")):
                    with self.assertRaises(fetch_article.ArticleFetchError) as ctx:
                        fetch_article.extract(gnews_url)
                self.assertIn("fetch_url 空応答", str(ctx.exception))

            # trafilatura.fetch_url が空応答でも昇格取得の HTML が十分なら通る
            long_text = "本文" * (config.MIN_BODY_CHARS)
            rescued = fetch_article.fetch_escalation.FetchResult(
                url=publisher,
                status=200,
                html="<html>rescued</html>",
                stage="fetcher",
                ok=True,
                attempts=[("urllib", 403, "blocked"), ("fetcher", 200, "ok")],
            )
            with patch.object(fetch_article.trafilatura, "fetch_url", return_value=""):
                with patch.object(fetch_article.fetch_escalation, "fetch_with_escalation",
                                  return_value=rescued):
                    with patch.object(fetch_article.trafilatura, "extract", return_value=long_text):
                        with patch.object(fetch_article.trafilatura, "extract_metadata", return_value=None):
                            result = fetch_article.extract(gnews_url)
            self.assertEqual(result["fetch_stage"], "fetcher")
            self.assertEqual(result["fetch_attempts"][0][0], "trafilatura")
            self.assertEqual(result["fetch_attempts"][1:], rescued.attempts)
            self.assertTrue(result["text"].startswith("本文"))

            # 昇格取得できても本文が短ければ採用しない
            with patch.object(fetch_article.trafilatura, "fetch_url", return_value=""):
                with patch.object(fetch_article.fetch_escalation, "fetch_with_escalation",
                                  return_value=rescued):
                    with patch.object(fetch_article.trafilatura, "extract",
                                      return_value="x" * (config.MIN_BODY_CHARS - 1)):
                        with patch.object(fetch_article.trafilatura, "extract_metadata", return_value=None):
                            with self.assertRaises(fetch_article.ArticleFetchError) as ctx:
                                fetch_article.extract(gnews_url)
            self.assertIn("本文短文", str(ctx.exception))

            # trafilatura.extract が短文を返すケース（MIN_BODY_CHARS 未満）
            short_text = "x" * (config.MIN_BODY_CHARS - 1)
            with patch.object(fetch_article.trafilatura, "fetch_url", return_value="<html>ok</html>"):
                with patch.object(fetch_article.trafilatura, "extract", return_value=short_text):
                    with patch.object(fetch_article.trafilatura, "extract_metadata", return_value=None):
                        with self.assertRaises(fetch_article.ArticleFetchError) as ctx:
                            fetch_article.extract(gnews_url)
                self.assertIn("本文短文", str(ctx.exception))

            # 十分な長さの本文は通る
            long_text = "本文" * (config.MIN_BODY_CHARS)  # MIN_BODY_CHARS*2 chars >= MIN_BODY_CHARS
            with patch.object(fetch_article.trafilatura, "fetch_url", return_value="<html>ok</html>"):
                with patch.object(fetch_article.trafilatura, "extract", return_value=long_text):
                    with patch.object(fetch_article.trafilatura, "extract_metadata", return_value=None):
                        result = fetch_article.extract(gnews_url)
            self.assertEqual(result["publisher_url"], publisher)
            self.assertTrue(result["text"].startswith("本文"))
            self.assertEqual(result["fetch_stage"], "trafilatura")
            # MAX_BODY_CHARS 超過は頭打ちされる
            self.assertLessEqual(len(result["text"]), config.MAX_BODY_CHARS)


if __name__ == "__main__":
    unittest.main()
