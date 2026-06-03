"""Google News redirect URL の publisher 解決と trafilatura 本文抽出の境界モジュール。

なぜ重要か（意図）:
  Google News の RSS link は JS リダイレクト中間ページ（urllib では publisher に解決不可・
  HTML 中の canonical / og:url も Google 内 URL のまま）。これを 1 箇所で必ず
  googlenewsdecoder.gnewsdecoder() に通して publisher URL に解決し、trafilatura で本文抽出する。
  短文（< config.MIN_BODY_CHARS）/ 失敗は ArticleFetchError で表現し、上位は当該記事をドロップする。
  RSS description などへのフォールバックはしない（品質優先）。
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

import trafilatura
from googlenewsdecoder import gnewsdecoder

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import config  # noqa: E402


class ArticleFetchError(Exception):
    """記事取得失敗（解決不可・本文短文・タイムアウト・例外）。上位はキャッチして当該記事をドロップ。"""


def resolve(gnews_url: str, *, interval: int = 1) -> str:
    """Google News URL を publisher URL に解決する。失敗時 ArticleFetchError。

    gnewsdecoder は内部で Google News の signed request を 2 段で叩いて publisher を取り出す。
    既に publisher URL（news.google.com 以外）が渡されたらそのまま返す。
    """
    if not gnews_url:
        raise ArticleFetchError("空 URL")
    host = urlparse(gnews_url).netloc.lower()
    if "news.google.com" not in host:
        return gnews_url  # 既に publisher URL
    try:
        decoded = gnewsdecoder(gnews_url, interval=interval)
    except Exception as exc:
        raise ArticleFetchError(f"decoder 例外: {type(exc).__name__}: {exc}") from exc
    if not decoded or not decoded.get("status"):
        raise ArticleFetchError(f"decoder 失敗: {decoded.get('message', '?') if decoded else 'None'}")
    pub_url = decoded.get("decoded_url", "")
    if not pub_url or not pub_url.startswith("http"):
        raise ArticleFetchError(f"decoded_url 不正: {pub_url!r}")
    return pub_url


def extract(gnews_url: str) -> dict:
    """gnews_url → publisher URL 解決 → trafilatura 本文抽出 → meta 整形。

    返り値: {"text": str, "publisher_url": str, "publisher_name": str, "og_image": str | None}
    失敗時は ArticleFetchError。本文が config.MIN_BODY_CHARS 未満も例外で落とす（paywall / 404 対策）。
    """
    publisher_url = resolve(gnews_url)
    try:
        html = trafilatura.fetch_url(publisher_url)
    except Exception as exc:
        raise ArticleFetchError(f"fetch_url 例外: {type(exc).__name__}: {exc}") from exc
    if not html:
        raise ArticleFetchError(f"fetch_url 空応答: {publisher_url}")
    try:
        text = trafilatura.extract(html, include_comments=False, include_tables=False)
    except Exception as exc:
        raise ArticleFetchError(f"extract 例外: {type(exc).__name__}: {exc}") from exc
    if not text or len(text) < config.MIN_BODY_CHARS:
        raise ArticleFetchError(
            f"本文短文（{len(text) if text else 0} 字 < {config.MIN_BODY_CHARS}）: {publisher_url}"
        )
    # MAX_BODY_CHARS で頭打ち（Gemini TPM 制御）
    if len(text) > config.MAX_BODY_CHARS:
        text = text[: config.MAX_BODY_CHARS]
    # メタデータ
    meta = None
    try:
        meta = trafilatura.extract_metadata(html)
    except Exception:
        meta = None
    publisher_name = ""
    og_image = None
    if meta:
        publisher_name = (getattr(meta, "sitename", "") or "") or _domain(publisher_url)
        og_image = getattr(meta, "image", None)
    if not publisher_name:
        publisher_name = _domain(publisher_url)
    return {
        "text": text,
        "publisher_url": publisher_url,
        "publisher_name": publisher_name,
        "og_image": og_image,
    }


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host.removeprefix("www.")
