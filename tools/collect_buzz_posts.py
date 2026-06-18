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


def _publishable_buzz(row: dict) -> bool:
    return (
        int(row.get("absolute_score") or row.get("buzz_score") or 0) >= BUZZPOST_MIN_ABSOLUTE_SCORE
        or float(row.get("velocity_score") or 0.0) >= BUZZPOST_MIN_VELOCITY_SCORE
    )


def _public_row(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in {"publishable", "drop_reason"}}


def _parse_buzzpost_items(
    xml_text: str,
    *,
    source_name: str,
    today: str,
    observed_at: datetime,
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
        text = _clean_text(fields.get("description") or fields.get("encoded") or "")
        if not text:
            continue
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
        row["publishable"] = _publishable_buzz(row)
        row["drop_reason"] = "" if row["publishable"] else "threshold"
        rows.append(row)
    return rows


def collect_from_rss_paths(
    rss_paths: str | None = None,
    *,
    request_text=_request_text,
    today: str | None = None,
    observed_at: str | datetime | None = None,
    include_unpublishable: bool = False,
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
                for row in _parse_buzzpost_items(xml_text, source_name=name, today=date_key, observed_at=observed_dt):
                    key = row["post_url"]
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(row)
        except Exception:
            degraded = True
            continue
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
            "dropped_duplicate": 0,
            "degraded": 0,
            "min_absolute_score": BUZZPOST_MIN_ABSOLUTE_SCORE,
            "min_velocity_score": BUZZPOST_MIN_VELOCITY_SCORE,
        }
    loaded = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    loaded.setdefault("min_absolute_score", BUZZPOST_MIN_ABSOLUTE_SCORE)
    loaded.setdefault("min_velocity_score", BUZZPOST_MIN_VELOCITY_SCORE)
    return loaded


def collect(
    *,
    rss_paths: str | None = None,
    output_path: Path = BUZZPOST_PATH,
    stats_path: Path | None = None,
    today: str | None = None,
    observed_at: str | datetime | None = None,
) -> dict:
    stats_path = stats_path or (
        BUZZPOST_STATS_PATH if output_path == BUZZPOST_PATH else output_path.with_name("buzz_posts_stats.json")
    )
    candidate_rows, degraded = collect_from_rss_paths(
        rss_paths,
        today=today,
        observed_at=observed_at,
        include_unpublishable=True,
    )
    rows = [row for row in candidate_rows if _publishable_buzz(row)]
    existing = _load_existing(output_path)
    by_url = {
        str(row.get("post_url")): row
        for row in existing
        if row.get("post_url") and _publishable_buzz(row)
    }
    for row in rows:
        by_url[row["post_url"]] = _public_row(row)
    merged = sorted(
        by_url.values(),
        key=lambda r: (r.get("date", ""), r.get("buzz_score", 0), r.get("published_at", "")),
        reverse=True,
    )[:120]
    _write_jsonl(output_path, merged)
    stats = {
        "latest": today or datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9))).date().isoformat(),
        "candidate_count": len(candidate_rows),
        "collected": len(rows),
        "written": len(merged),
        "dropped_threshold": len([row for row in candidate_rows if not _publishable_buzz(row)]),
        "dropped_duplicate": 0,
        "degraded": int(degraded),
        "min_absolute_score": BUZZPOST_MIN_ABSOLUTE_SCORE,
        "min_velocity_score": BUZZPOST_MIN_VELOCITY_SCORE,
    }
    _write_stats(stats_path, stats)
    return stats


def load_public_rows(path: Path = BUZZPOST_PATH, *, limit: int = 80) -> list[dict]:
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
