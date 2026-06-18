"""BuzzPost: X RSS から生成AIコミュニティの話題投稿を収集する。"""
from __future__ import annotations

import email.utils
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BUZZPOST_PATH = DATA / "buzz_posts.jsonl"
BUZZPOST_STATS_PATH = DATA / "buzz_posts_stats.json"
DEFAULT_X_RSS_DIR = ROOT.parent / "twitter-rss" / "output"
BUZZPOST_MIN_ABSOLUTE_SCORE = int(os.environ.get("BUZZPOST_MIN_ABSOLUTE_SCORE", "25"))
BUZZPOST_MIN_VELOCITY_SCORE = float(os.environ.get("BUZZPOST_MIN_VELOCITY_SCORE", "8"))
BUZZPOST_EXCLUDED_HASHTAG_RE = re.compile(r"(?:[#＃]\s*AIイラスト|絵師)", re.IGNORECASE)
BUZZPOST_PREVIEW_LIMIT = int(os.environ.get("BUZZPOST_PREVIEW_LIMIT", "2"))
BUZZPOST_HISTORY_LIMIT = int(os.environ.get("BUZZPOST_HISTORY_LIMIT", "160"))
X_OEMBED_URL = "https://publish.twitter.com/oembed"

CAT_META = {
    "model": {"label": "モデル/LLM", "glyph": "◆"},
    "editor": {"label": "AIエディタ・コーディング", "glyph": "▲"},
    "media": {"label": "画像・動画・音声生成", "glyph": "◎"},
    "agent": {"label": "エージェント・ツール", "glyph": "■"},
}
SOURCE_CATEGORIES = {
    "buzzpost-model": "model",
    "buzzpost-editor": "editor",
    "buzzpost-agent": "agent",
    "buzzpost-media": "media",
}


def _load_local_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_local_env()


def _request_text(url: str, *, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "AI-Pulse-BuzzPost/0.1"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _split_rss_locations(raw_paths: str) -> list[str]:
    return [part.strip() for part in re.split(r"[\r\n;]+", raw_paths or "") if part.strip()]


def _default_rss_paths() -> str:
    return os.environ.get("BUZZPOST_X_RSS_PATHS") or str(DEFAULT_X_RSS_DIR)


def _iter_rss_xml(location: str, *, request_text=_request_text) -> list[tuple[str, str]]:
    if location.startswith(("http://", "https://")):
        name = urllib.parse.urlparse(location).path.rsplit("/", 1)[-1] or "remote"
        return [(Path(name).stem, request_text(location))]
    path = Path(location).expanduser()
    if path.is_dir():
        return [(p.stem, p.read_text(encoding="utf-8", errors="replace")) for p in sorted(path.glob("*.xml"))]
    return [(path.stem, path.read_text(encoding="utf-8", errors="replace"))]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _parse_rss_datetime(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(
                tzinfo=timezone(timedelta(hours=9))
            ).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _clean_text(value: str) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
    text = re.sub(r"(?i)</\s*(p|div|li|blockquote)\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def _extract_media_urls(value: str) -> list[str]:
    text = html.unescape(value or "")
    urls: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"""(?is)<img\b[^>]*\bsrc\s*=\s*["']([^"']+)["']""", text):
        url = match.group(1).strip()
        if not url.startswith("https://pbs.twimg.com/"):
            continue
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def _extract_profile_image_url(item: ET.Element) -> str:
    for child in list(item):
        name = _local_name(child.tag)
        if name not in {"thumbnail", "avatar", "image"}:
            continue
        url = (child.attrib.get("url") or child.attrib.get("href") or "").strip()
        if url.startswith("https://pbs.twimg.com/profile_images/"):
            return url
    return ""


def _handle_from_url(post_url: str) -> str:
    match = re.search(r"(?:x|twitter)\.com/([^/]+)/status/", post_url, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _parse_author(value: str, post_url: str) -> tuple[str, str]:
    text = _clean_text(value or "")
    match = re.search(r"\(@([A-Za-z0-9_]{1,32})\)\s*$", text)
    if match:
        name = text[: match.start()].strip() or match.group(1)
        return name, match.group(1)
    handle = _handle_from_url(post_url)
    return (text or handle or "X user"), handle


def _profile_image_fallback(handle: str) -> str:
    if not handle:
        return ""
    return f"https://unavatar.io/x/{urllib.parse.quote(handle)}"


_TEXT_URL_RE = re.compile(r"https?://[^\s<>\"]+")


def _extract_text_urls(text: str, *, post_url: str = "") -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for match in _TEXT_URL_RE.finditer(text or ""):
        url = match.group(0).rstrip(".,、。)]）")
        if url == post_url:
            continue
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def _meta_content(html_text: str, key: str) -> str:
    pattern = (
        rf"""(?is)<meta\b(?=[^>]*(?:property|name)\s*=\s*["']{re.escape(key)}["'])"""
        rf"""(?=[^>]*content\s*=\s*["']([^"']+)["'])[^>]*>"""
    )
    match = re.search(pattern, html_text or "")
    return html.unescape(match.group(1).strip()) if match else ""


def _link_preview(url: str, *, request_text=_request_text) -> dict | None:
    try:
        page = request_text(url, timeout=12)
    except Exception:
        return None
    image_url = _meta_content(page, "og:image") or _meta_content(page, "twitter:image")
    if not image_url:
        return None
    image_url = urllib.parse.urljoin(url, image_url)
    if not image_url.startswith(("http://", "https://")):
        return None
    return {
        "url": url,
        "title": _meta_content(page, "og:title") or _meta_content(page, "twitter:title"),
        "site_name": _meta_content(page, "og:site_name"),
        "image_url": image_url,
    }


def _link_previews(text: str, *, post_url: str, request_text=_request_text) -> list[dict]:
    previews: list[dict] = []
    for url in _extract_text_urls(text, post_url=post_url)[:BUZZPOST_PREVIEW_LIMIT]:
        preview = _link_preview(url, request_text=request_text)
        if preview:
            previews.append(preview)
    return previews


def _sanitize_x_oembed_html(value: str) -> str:
    embed = re.sub(r"(?is)<script\b[^>]*>.*?</script>", "", value or "").strip()
    if not embed.lower().startswith('<blockquote class="twitter-tweet"'):
        return ""
    if "<script" in embed.lower() or "<iframe" in embed.lower():
        return ""
    return embed


def _x_oembed_html(post_url: str, *, request_text=_request_text) -> str:
    if not post_url.startswith(("https://x.com/", "https://twitter.com/")):
        return ""
    params = urllib.parse.urlencode(
        {
            "url": post_url,
            "theme": "dark",
            "dnt": "true",
            "omit_script": "true",
            "hide_thread": "false",
        }
    )
    try:
        payload = json.loads(request_text(f"{X_OEMBED_URL}?{params}", timeout=12))
    except Exception:
        return ""
    if str(payload.get("provider_name") or "").lower() not in {"x", "twitter"}:
        return ""
    return _sanitize_x_oembed_html(str(payload.get("html") or ""))


def _mostly_english(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    if len(compact) < 12:
        return False
    ascii_count = sum(1 for ch in compact if ord(ch) < 128)
    cjk_count = sum(1 for ch in compact if "\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff")
    return ascii_count / len(compact) >= 0.82 and cjk_count == 0


def _default_translate_text_ja(text: str) -> str:
    try:
        import llm_hybrid  # type: ignore

        return llm_hybrid.translate_buzzpost_text_ja(text)
    except Exception:
        return ""


def _observed_datetime(value: str | datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def _buzz_metrics(text: str) -> dict[str, int]:
    s = text.lower()
    metrics = {"likes": 0, "reposts": 0, "replies": 0, "quotes": 0}
    for pattern, weight in (
        (r"(\d+)\s*(?:likes?|いいね)", "likes"),
        (r"(\d+)\s*(?:reposts?|retweets?|rt|リポスト)", "reposts"),
        (r"(\d+)\s*(?:replies|reply|comments?|返信)", "replies"),
        (r"(\d+)\s*(?:quotes?|引用)", "quotes"),
    ):
        metrics[weight] += sum(int(m.group(1)) for m in re.finditer(pattern, s))
    return metrics


def _absolute_score(metrics: dict[str, int]) -> int:
    return (
        int(metrics.get("likes", 0))
        + int(metrics.get("reposts", 0)) * 2
        + int(metrics.get("replies", 0)) * 2
        + int(metrics.get("quotes", 0)) * 2
    )


def _query_min_faves(source_query: str) -> int:
    match = re.search(r"\bmin_faves:(\d+)\b", source_query or "", flags=re.IGNORECASE)
    return int(match.group(1)) if match else 0


def _velocity_score(score: int, published: datetime | None, observed_at: datetime) -> float:
    if not published or score <= 0:
        return 0.0
    published_utc = published.astimezone(timezone.utc)
    observed_utc = observed_at.astimezone(timezone.utc)
    age_hours = max((observed_utc - published_utc).total_seconds() / 3600, 1.0)
    return score / age_hours


def _base_buzz_score(row: dict) -> float:
    return float(row.get("absolute_score") or 0) + float(row.get("velocity_score") or 0.0)


def _apply_relative_scores(rows: list[dict]) -> None:
    publishable_rows = [row for row in rows if _publishable_buzz(row)]
    if not publishable_rows:
        return
    base_scores = [_base_buzz_score(row) for row in publishable_rows]
    min_score = min(base_scores)
    max_score = max(base_scores)
    score_range = max_score - min_score
    for row, base_score in zip(publishable_rows, base_scores):
        if score_range <= 0:
            relative_score = 0
        else:
            relative_score = int(round(((base_score - min_score) / score_range) * 50))
        row["relative_score"] = relative_score
        row["buzz_score"] = int(round(base_score + relative_score))


def _publishable_buzz(row: dict) -> bool:
    if _excluded_buzzpost_text(str(row.get("text") or "")):
        return False
    return (
        int(row.get("absolute_score") or row.get("buzz_score") or 0) >= BUZZPOST_MIN_ABSOLUTE_SCORE
        or float(row.get("velocity_score") or 0.0) >= BUZZPOST_MIN_VELOCITY_SCORE
    )


def _excluded_buzzpost_text(text: str) -> bool:
    return bool(BUZZPOST_EXCLUDED_HASHTAG_RE.search(text or ""))


def _public_row(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in {"publishable", "drop_reason"}}


def _history_key(row: dict) -> tuple[str, str]:
    return (str(row.get("date") or ""), str(row.get("post_url") or ""))


def _parse_buzzpost_items(
    xml_text: str,
    *,
    source_name: str,
    today: str,
    observed_at: datetime,
    request_text=_request_text,
    fetch_link_previews: bool = False,
    fetch_x_embeds: bool = False,
    translate_text_ja=None,
) -> list[dict]:
    cat = SOURCE_CATEGORIES.get(source_name)
    if not cat:
        return []
    root = ET.fromstring(xml_text)
    channel = next((node for node in root.iter() if _local_name(node.tag) == "channel"), None)
    channel_fields = {
        _local_name(child.tag): (child.text or "")
        for child in list(channel if channel is not None else [])
        if _local_name(child.tag) != "item"
    }
    source_query = channel_fields.get("description") or channel_fields.get("title") or ""
    query_min_faves = _query_min_faves(source_query)
    meta = CAT_META[cat]
    rows: list[dict] = []
    for item in root.iter():
        if _local_name(item.tag) != "item":
            continue
        fields = {_local_name(child.tag): (child.text or "") for child in list(item)}
        post_url = fields.get("link") or fields.get("guid") or ""
        if "x.com/" not in post_url and "twitter.com/" not in post_url:
            continue
        content_html = fields.get("description") or fields.get("encoded") or ""
        text = _clean_text(content_html)
        if not text:
            continue
        text_original = text
        translated = False
        if translate_text_ja and _mostly_english(text_original):
            translated_text = (translate_text_ja(text_original) or "").strip()
            if translated_text and translated_text != text_original:
                text = translated_text
                translated = True
        media_urls = _extract_media_urls(content_html)
        published = _parse_rss_datetime(fields.get("pubdate") or fields.get("title") or "")
        metrics = _buzz_metrics(text)
        absolute_score = _absolute_score(metrics)
        score_basis = "embedded_metrics"
        if absolute_score <= 0 and query_min_faves > 0:
            absolute_score = query_min_faves
            score_basis = "query_min_faves"
        velocity_score = _velocity_score(absolute_score, published, observed_at)
        row = {
            "date": today,
            "category": cat,
            "category_label": meta["label"],
            "glyph": meta["glyph"],
            "source": f"x-rss:{source_name}",
            "source_query": source_query,
            "post_url": post_url,
            "title": _clean_text(fields.get("title") or text[:80]),
            "text": text,
            "published_at": published.astimezone(timezone.utc).isoformat() if published else "",
            "buzz_score": int(round(absolute_score + velocity_score)),
            "absolute_score": absolute_score,
            "velocity_score": round(velocity_score, 2),
            "score_basis": score_basis,
            "engagement": metrics,
        }
        author_name, author_handle = _parse_author(fields.get("creator") or fields.get("author") or "", post_url)
        profile_image_url = _extract_profile_image_url(item)
        if author_name:
            row["author_name"] = author_name
        if author_handle:
            row["author_handle"] = f"@{author_handle}"
        if profile_image_url:
            row["profile_image_url"] = profile_image_url
        elif author_handle:
            row["profile_image_url"] = _profile_image_fallback(author_handle)
        if translated:
            row["text_original"] = text_original
            row["translated"] = True
        if fetch_link_previews:
            link_previews = _link_previews(text_original, post_url=post_url, request_text=request_text)
            if link_previews:
                row["link_previews"] = link_previews
        if media_urls:
            row["media_urls"] = media_urls
        row["publishable"] = _publishable_buzz(row)
        row["drop_reason"] = "" if row["publishable"] else ("excluded_hashtag" if _excluded_buzzpost_text(text) else "threshold")
        if fetch_x_embeds and row["publishable"]:
            embed_html = _x_oembed_html(post_url, request_text=request_text)
            if embed_html:
                row["x_embed_html"] = embed_html
        rows.append(row)
    return rows


def collect_from_rss_paths(
    rss_paths: str | None = None,
    *,
    request_text=_request_text,
    today: str | None = None,
    observed_at: str | datetime | None = None,
    include_unpublishable: bool = False,
    fetch_link_previews: bool = False,
    fetch_x_embeds: bool = False,
    translate_text_ja=None,
) -> tuple[list[dict], bool]:
    raw_paths = rss_paths if rss_paths is not None else _default_rss_paths()
    locations = _split_rss_locations(raw_paths)
    if not locations:
        return [], False
    observed_dt = _observed_datetime(observed_at)
    date_key = today or datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9))).date().isoformat()
    rows: list[dict] = []
    degraded = False
    seen: set[str] = set()
    for location in locations:
        try:
            for name, xml_text in _iter_rss_xml(location, request_text=request_text):
                for row in _parse_buzzpost_items(
                    xml_text,
                    source_name=name,
                    today=date_key,
                    observed_at=observed_dt,
                    request_text=request_text,
                    fetch_link_previews=fetch_link_previews,
                    fetch_x_embeds=fetch_x_embeds,
                    translate_text_ja=translate_text_ja,
                ):
                    key = row["post_url"]
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(row)
        except Exception:
            degraded = True
            continue
    _apply_relative_scores(rows)
    public_rows = rows if include_unpublishable else [_public_row(row) for row in rows if _publishable_buzz(row)]
    public_rows.sort(key=lambda r: (r.get("date", ""), r.get("buzz_score", 0), r.get("published_at", "")), reverse=True)
    return public_rows, degraded


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _load_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _write_stats(path: Path, stats: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_stats(path: Path = BUZZPOST_STATS_PATH) -> dict:
    if not path.exists():
        return {
            "latest": "",
            "candidate_count": 0,
            "collected": 0,
            "written": 0,
            "dropped_threshold": 0,
            "dropped_excluded": 0,
            "dropped_duplicate": 0,
            "degraded": 0,
            "min_absolute_score": BUZZPOST_MIN_ABSOLUTE_SCORE,
            "min_velocity_score": BUZZPOST_MIN_VELOCITY_SCORE,
        }
    loaded = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    loaded.setdefault("min_absolute_score", BUZZPOST_MIN_ABSOLUTE_SCORE)
    loaded.setdefault("min_velocity_score", BUZZPOST_MIN_VELOCITY_SCORE)
    loaded.setdefault("dropped_excluded", 0)
    return loaded


def collect(
    *,
    rss_paths: str | None = None,
    output_path: Path = BUZZPOST_PATH,
    stats_path: Path | None = None,
    today: str | None = None,
    observed_at: str | datetime | None = None,
    fetch_link_previews: bool | None = None,
    fetch_x_embeds: bool | None = None,
    translate_text_ja=None,
) -> dict:
    stats_path = stats_path or (
        BUZZPOST_STATS_PATH if output_path == BUZZPOST_PATH else output_path.with_name("buzz_posts_stats.json")
    )
    real_output = output_path == BUZZPOST_PATH
    if fetch_link_previews is None:
        fetch_link_previews = real_output
    if fetch_x_embeds is None:
        fetch_x_embeds = real_output
    if translate_text_ja is None and real_output:
        translate_text_ja = _default_translate_text_ja
    candidate_rows, degraded = collect_from_rss_paths(
        rss_paths,
        today=today,
        observed_at=observed_at,
        include_unpublishable=True,
        fetch_link_previews=fetch_link_previews,
        fetch_x_embeds=fetch_x_embeds,
        translate_text_ja=translate_text_ja,
    )
    rows = [row for row in candidate_rows if _publishable_buzz(row)]
    existing = _load_existing(output_path)
    by_history_key = {
        _history_key(row): row
        for row in existing
        if row.get("post_url") and _publishable_buzz(row)
    }
    for row in rows:
        by_history_key[_history_key(row)] = _public_row(row)
    merged = sorted(
        by_history_key.values(),
        key=lambda r: (r.get("date", ""), r.get("buzz_score", 0), r.get("published_at", "")),
        reverse=True,
    )[:BUZZPOST_HISTORY_LIMIT]
    _write_jsonl(output_path, merged)
    stats = {
        "latest": today or datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9))).date().isoformat(),
        "candidate_count": len(candidate_rows),
        "collected": len(rows),
        "written": len(merged),
        "dropped_threshold": len([row for row in candidate_rows if row.get("drop_reason") == "threshold"]),
        "dropped_excluded": len([row for row in candidate_rows if row.get("drop_reason") == "excluded_hashtag"]),
        "dropped_duplicate": 0,
        "degraded": int(degraded),
        "min_absolute_score": BUZZPOST_MIN_ABSOLUTE_SCORE,
        "min_velocity_score": BUZZPOST_MIN_VELOCITY_SCORE,
    }
    _write_stats(stats_path, stats)
    return stats


def load_public_rows(path: Path = BUZZPOST_PATH, *, limit: int = BUZZPOST_HISTORY_LIMIT) -> list[dict]:
    rows = [row for row in _load_existing(path) if _publishable_buzz(row)]
    rows.sort(key=lambda r: (r.get("date", ""), r.get("buzz_score", 0), r.get("published_at", "")), reverse=True)
    return rows[:limit]


def main() -> None:
    stats = collect()
    print(
        "[buzzpost] "
        f"collected={stats['collected']} written={stats['written']} degraded={stats['degraded']}"
    )


if __name__ == "__main__":
    main()
