"""定量値の一次ソース裏取り: 主張値が引用元ページに実在するかをクロールして確認。

ベンチ / star / 価格などの定量値は LLM 幻覚のリスクが高い。掲載前に一次ソース（カルテ/デルタの
source URL）を取得し、主張値が本文に現れるかを機械的に確認する。
WebFetch は LLM 要約で <meta> や数値を落とすため使わない（memory feedback_webfetch_ogp_unfit）。
urllib + html.parser で生テキストを取り、正規化した数値表現の包含で判定する。

判定は「材料」であって最終判定ではない。誤検出を避けるため緩めに正規化（カンマ/全角/空白ゆれを
吸収）し、verified=False（＝本文に見当たらない＝幻覚の疑い）を人/LLM の再確認トリガーに使う。
fetcher はテストで差し替え可能。
"""
from __future__ import annotations

import re
import urllib.request
from html.parser import HTMLParser

_UA = "AI-Pulse-verify/1.0 (+https://github.com)"


class _TextExtractor(HTMLParser):
    """script/style を除いた可視テキストだけを集める。"""

    def __init__(self):
        super().__init__()
        self._buf = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self._buf.append(data)

    def text(self) -> str:
        return " ".join("".join(self._buf).split())


def fetch_text(url, *, timeout=20) -> str:
    """URL の本文を可視テキストとして取得（utf-8 / errors=replace）。"""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (http(s) のみ想定)
        raw = r.read()
    parser = _TextExtractor()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return parser.text()


def _normalize_number(s: str) -> str:
    """全角→半角、カンマ/空白除去。'1,000,000' と '1000000' を一致させる。"""
    s = str(s).translate(str.maketrans("０１２３４５６７８９．", "0123456789."))
    return re.sub(r"[,\s]", "", s)


def verify(claim_value, source_url, *, fetcher=fetch_text) -> dict:
    """claim_value（例 '128000' / '1,000,000' / '$20'）が source_url 本文に現れるか確認。

    返り値: {'verified': bool, 'needle': str, 'url': str}
    """
    text = fetcher(source_url)
    needle = _normalize_number(claim_value)
    haystack = _normalize_number(text)
    verified = bool(needle) and needle in haystack
    return {"verified": verified, "needle": needle, "url": source_url}
