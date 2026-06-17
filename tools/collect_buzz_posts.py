"""BuzzPost: X RSS から生成AIコミュニティの話題投稿を収集する。"""
from __future__ import annotations

import email.utils
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BUZZPOST_PATH = DATA / "buzz_posts.jsonl"
DEFAULT_X_RSS_DIR = ROOT.parent / "twitter-rss" / "output"

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
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", text).strip()


def _buzz_score(text: str) -> int:
    s = text.lower()
    score = 0
    for pattern, weight in (
        (r"(\d+)\s*(?:likes?|いいね)", 1),
        (r"(\d+)\s*(?:reposts?|retweets?|rt|リポスト)", 2),
        (r"(\d+)\s*(?:replies|reply|comments?|返信)", 2),
        (r"(\d+)\s*(?:quotes?|引用)", 2),
    ):
        for m in re.finditer(pattern, s):
            score += int(m.group(1)) * weight
    return score


def _parse_buzzpost_items(xml_text: str, *, source_name: str, today: str) -> list[dict]:
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
    meta = CAT_META[cat]
    rows: list[dict] = []
    for item in root.iter():
        if _local_name(item.tag) != "item":
            continue
        fields = {_local_name(child.tag): (child.text or "") for child in list(item)}
        post_url = fields.get("link") or fields.get("guid") or ""
        if "x.com/" not in post_url and "twitter.com/" not in post_url:
            continue
        text = _clean_text(fields.get("description") or fields.get("encoded") or "")
        if not text:
            continue
        published = _parse_rss_datetime(fields.get("pubdate") or fields.get("title") or "")
        rows.append({
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
            "buzz_score": _buzz_score(text),
        })
    return rows


def collect_from_rss_paths(
    rss_paths: str | None = None,
    *,
    request_text=_request_text,
    today: str | None = None,
) -> tuple[list[dict], bool]:
    raw_paths = rss_paths if rss_paths is not None else _default_rss_paths()
    locations = _split_rss_locations(raw_paths)
    if not locations:
        return [], False
    date_key = today or datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9))).date().isoformat()
    rows: list[dict] = []
    degraded = False
    seen: set[str] = set()
    for location in locations:
        try:
            for name, xml_text in _iter_rss_xml(location, request_text=request_text):
                for row in _parse_buzzpost_items(xml_text, source_name=name, today=date_key):
                    key = row["post_url"]
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(row)
        except Exception:
            degraded = True
            continue
    rows.sort(key=lambda r: (r.get("date", ""), r.get("buzz_score", 0), r.get("published_at", "")), reverse=True)
    return rows, degraded


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


def collect(
    *,
    rss_paths: str | None = None,
    output_path: Path = BUZZPOST_PATH,
    today: str | None = None,
) -> dict:
    rows, degraded = collect_from_rss_paths(rss_paths, today=today)
    existing = _load_existing(output_path)
    by_url = {str(row.get("post_url")): row for row in existing if row.get("post_url")}
    for row in rows:
        by_url[row["post_url"]] = row
    merged = sorted(
        by_url.values(),
        key=lambda r: (r.get("date", ""), r.get("buzz_score", 0), r.get("published_at", "")),
        reverse=True,
    )[:120]
    _write_jsonl(output_path, merged)
    return {"collected": len(rows), "written": len(merged), "degraded": int(degraded)}


def load_public_rows(path: Path = BUZZPOST_PATH, *, limit: int = 80) -> list[dict]:
    rows = _load_existing(path)
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
