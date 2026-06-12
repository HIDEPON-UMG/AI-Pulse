"""記事 HTML 取得の昇格境界。

通常の取得で blocked / 空応答になった時だけ Scrapling に昇格する。
本文抽出そのものは fetch_article.py 側の trafilatura 契約を維持する。
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_TIMEOUT_SEC = 20.0
DEFAULT_STEALTHY_BUDGET = 5
_stealthy_used = 0

_BLOCKED_STATUS = {403, 429, 503}
_BLOCKED_MARKERS = (
    "cloudflare",
    "cf-chl",
    "turnstile",
    "access denied",
    "attention required",
    "verify you are human",
    "captcha",
)


@dataclass
class FetchResult:
    """取得昇格ラダーの結果。"""

    url: str
    status: int | None = None
    html: str | None = None
    stage: str = "none"
    ok: bool = False
    blocked: bool = False
    error: str | None = None
    elapsed_sec: float = 0.0
    attempts: list[tuple[str, int | None, str]] = field(default_factory=list)


def _looks_blocked(status: int | None, html: str | None) -> bool:
    if status in _BLOCKED_STATUS:
        return True
    if not html:
        return False
    lower = html[:20000].lower()
    return any(marker in lower for marker in _BLOCKED_MARKERS)


def _read_error_body(exc: urllib.error.HTTPError) -> str | None:
    try:
        raw = exc.read(65536)
    except Exception:
        return None
    try:
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return None


def _fetch_urllib(url: str, timeout: float) -> tuple[int | None, str | None, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.status, raw.decode(charset, errors="replace"), "ok"
    except urllib.error.HTTPError as exc:
        return exc.code, _read_error_body(exc), f"http error: {exc.code}"
    except Exception as exc:
        return None, None, f"urllib 例外: {type(exc).__name__}: {exc}"


def _extract_html_from_page(page: object) -> str | None:
    for attr in ("html", "body", "text", "content"):
        value = getattr(page, attr, None)
        if callable(value):
            try:
                value = value()
            except Exception:
                value = None
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if isinstance(value, str) and value:
            return value
    return str(page) if page is not None else None


def _fetch_scrapling(
    url: str,
    timeout: float,
    *,
    stealthy: bool,
) -> tuple[int | None, str | None, str]:
    try:
        from scrapling.fetchers import Fetcher, StealthyFetcher
    except Exception as exc:
        return None, None, f"scrapling 未導入: {type(exc).__name__}"

    try:
        if stealthy:
            page = StealthyFetcher.fetch(
                url,
                headless=True,
                network_idle=True,
                timeout=int(timeout * 1000),
            )
        else:
            page = Fetcher.get(
                url,
                stealthy_headers=True,
                timeout=timeout,
            )
    except Exception as exc:
        stage = "stealthy" if stealthy else "fetcher"
        return None, None, f"{stage} 例外: {type(exc).__name__}: {exc}"

    return getattr(page, "status", None), _extract_html_from_page(page), "ok"


def _stealthy_budget(default: int) -> int:
    raw = os.environ.get("AI_PULSE_STEALTHY_BUDGET")
    if raw is None:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _finalize(
    result: FetchResult,
    stage: str,
    status: int | None,
    html: str | None,
    started: float,
    *,
    blocked: bool,
    error: str | None = None,
) -> FetchResult:
    result.stage = stage
    result.status = status
    result.html = html
    result.ok = status is not None and 200 <= status < 300 and bool(html) and not blocked
    result.blocked = blocked
    result.error = error
    result.elapsed_sec = round(time.monotonic() - started, 3)
    return result


def fetch_with_escalation(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SEC,
    stealthy_budget: int = DEFAULT_STEALTHY_BUDGET,
) -> FetchResult:
    """urllib -> Scrapling Fetcher -> StealthyFetcher の順で HTML を取得する。"""
    global _stealthy_used
    started = time.monotonic()
    result = FetchResult(url=url)

    scheme = urllib.parse.urlsplit(url).scheme.lower()
    if scheme not in ("http", "https"):
        note = f"unsupported scheme: {scheme or '(empty)'}"
        result.attempts.append(("guard", None, note))
        return _finalize(result, "guard", None, None, started, blocked=False, error=note)

    status, html, note = _fetch_urllib(url, timeout)
    result.attempts.append(("urllib", status, note))
    blocked = _looks_blocked(status, html)
    if status is not None and 200 <= status < 300 and html and not blocked:
        return _finalize(result, "urllib", status, html, started, blocked=False)
    if status is not None and not blocked and status >= 400:
        return _finalize(result, "urllib", status, html, started, blocked=False, error=note)

    status2, html2, note2 = _fetch_scrapling(url, timeout, stealthy=False)
    result.attempts.append(("fetcher", status2, note2))
    blocked2 = _looks_blocked(status2, html2)
    if status2 is not None and 200 <= status2 < 300 and html2 and not blocked2:
        return _finalize(result, "fetcher", status2, html2, started, blocked=False)
    if status2 is not None and not blocked2 and status2 >= 400:
        return _finalize(result, "fetcher", status2, html2, started, blocked=False, error=note2)

    budget = _stealthy_budget(stealthy_budget)
    if _stealthy_used >= budget:
        return _finalize(
            result,
            "fetcher",
            status2,
            html2,
            started,
            blocked=True,
            error=f"StealthyFetcher 上限 {budget} 件超過のため昇格拒否",
        )
    _stealthy_used += 1
    status3, html3, note3 = _fetch_scrapling(url, timeout, stealthy=True)
    result.attempts.append(("stealthy", status3, note3))
    blocked3 = _looks_blocked(status3, html3)
    if status3 is not None and 200 <= status3 < 300 and html3 and not blocked3:
        return _finalize(result, "stealthy", status3, html3, started, blocked=False)

    return _finalize(
        result,
        "stealthy",
        status3,
        html3,
        started,
        blocked=blocked3 or status3 is None,
        error=note3 if note3 != "ok" else "全段で取得失敗",
    )
