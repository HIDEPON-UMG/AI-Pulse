"""GitHub Pages の公開 HTML が期待日の SSG 出力か確認する。"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request

try:
    from . import config
except ImportError:
    import config


class FreshnessError(Exception):
    """公開 freshness gate の失敗。"""


def extract_build_date(html: str) -> str:
    match = re.search(
        r'<script[^>]+id=["\']ssg-meta["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        raise FreshnessError("ssg-meta not found")
    try:
        meta = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise FreshnessError(f"ssg-meta json parse failed: {exc}") from exc
    build = str(meta.get("build") or "").strip()
    if not build:
        raise FreshnessError("ssg-meta build is empty")
    return build


def check_html(html: str, *, expected_date: str) -> None:
    actual = extract_build_date(html)
    if actual != expected_date:
        raise FreshnessError(f"public build date mismatch: expected={expected_date} actual={actual}")


def fetch_html(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AI-Pulse-public-freshness/1.0",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def wait_until_fresh(url: str, *, expected_date: str, attempts: int, interval: float) -> None:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            check_html(fetch_html(f"{url}?freshness={expected_date}-{attempt}"), expected_date=expected_date)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < attempts:
                time.sleep(interval)
    raise FreshnessError(f"public freshness check failed after {attempts} attempts: {last_error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=config.SITE_URL)
    parser.add_argument("--expected-date", required=True)
    parser.add_argument("--attempts", type=int, default=20)
    parser.add_argument("--interval", type=float, default=15.0)
    args = parser.parse_args(argv)

    url = args.url.rstrip("/") + "/index.html"
    try:
        wait_until_fresh(
            url,
            expected_date=args.expected_date,
            attempts=args.attempts,
            interval=args.interval,
        )
    except FreshnessError as exc:
        print(f"[check_public_freshness] ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"[check_public_freshness] OK: {url} build={args.expected_date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
