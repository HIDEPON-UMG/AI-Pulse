"""日次速報ジョブ: Google News RSS -> L2 events -> store.ingest_events

claude -p / SDK 不使用。標準ライブラリ（urllib + xml）のみ依存。
entities.jsonl の name/vendor からクエリを自動生成（QUERY_OVERRIDES で上書き可能）。
Task Scheduler から run_daily.py 経由で毎日 7:00 に実行。
"""
from __future__ import annotations

import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import config  # noqa: E402
import schema  # noqa: E402
import store  # noqa: E402

DATA = ROOT / "data"

# 自動生成クエリを上書き（日本語名 entity など ASCII 変換が難しいもの）
QUERY_OVERRIDES: dict[str, str] = {
    "japan-ai-act": "Japan AI Basic Act regulation 2026",
    "qwen": "Alibaba Qwen AI model Tongyi",
}

# ドメイン -> source_tier 判定
_T1_DOMAINS = frozenset({
    "anthropic.com", "openai.com", "google.com", "deepmind.com", "googleblog.com",
    "meta.com", "microsoft.com", "nvidia.com", "figureai.com",
    "physicalintelligence.ai", "cognition.ai", "eu.europa.eu",
    "digital.go.jp", "meti.go.jp", "cursor.sh", "codeium.com",
    "blackforestlabs.ai", "runwayml.com", "langchain.com",
    "deepseek.com", "alibabacloud.com", "llama.meta.com",
})
_T2_DOMAINS = frozenset({
    "techcrunch.com", "theverge.com", "wired.com", "reuters.com",
    "bloomberg.com", "wsj.com", "arstechnica.com", "venturebeat.com",
    "thenextweb.com", "zdnet.com", "cnet.com", "tomsguide.com",
    "9to5google.com", "9to5mac.com", "engadget.com", "gizmodo.com",
})

# タイトル/概要 -> event_type（先にマッチしたものを採用）
_TYPE_PATTERNS: list[tuple[str, str]] = [
    (r"\b(acqui(?:re|red|sition)|merger|M&A)\b", "ma"),
    (r"\b(shut(?:down|ting)|clos(?:e|ed|ing|ure)|discontinu|end of service)\b", "shutdown"),
    (r"\b(outage|incident|breach|hack|vuln(?:erability)?|leak)\b", "incident"),
    (r"\b(benchmark|score|MMLU|HumanEval|Arena|Elo|leaderboard)\b", "benchmark"),
    (r"\b(fund(?:ing|ed)|invest(?:ment|ed)|rais(?:e|ed)|Series [A-E]|seed round|IPO)\b", "funding"),
    (r"\b(pric(?:e|ed|ing)|subscription|tier|plan|fee)\b", "pricing"),
    (r"\b(regulat|law|act|policy|bill|enforcement|guidance|compliance)\b", "regulation"),
]


def _infer_event_type(title: str, summary: str) -> str:
    text = f"{title} {summary}"
    for pat, etype in _TYPE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return etype
    return "release"


def _score_and_importance(title: str, source_name: str, event_type: str) -> tuple[int, str]:
    score = 50
    high_sources = {
        "techcrunch", "reuters", "bloomberg", "the verge", "wired",
        "ars technica", "venturebeat", "wsj", "financial times",
    }
    if any(s in source_name.lower() for s in high_sources):
        score += 15
    bonus = {
        "funding": 20, "ma": 20, "shutdown": 15, "benchmark": 10,
        "regulation": 10, "incident": 10, "pricing": 5, "release": 0,
    }
    score = min(100, score + bonus.get(event_type, 0))
    importance = "high" if score >= 70 else "mid" if score >= 50 else "low"
    return score, importance


def _source_tier(url: str) -> str:
    domain = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    if domain in _T1_DOMAINS:
        return "T1"
    if any(t2 in domain for t2 in _T2_DOMAINS):
        return "T2"
    return "T3"


def _fetch_rss(query: str, num: int = 5) -> list[dict]:
    """Google News RSS から最新記事を取得。失敗時は空リストを返す。"""
    q = urllib.parse.quote_plus(query)
    url = (
        f"https://news.google.com/rss/search"
        f"?q={q}&hl=en-US&gl=US&ceid=US:en&num={num}"
    )
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (compatible; AI-Pulse/1.0)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            xml_bytes = resp.read()
    except Exception as exc:
        print(f"    RSS 取得失敗: {exc}", file=sys.stderr)
        return []

    items: list[dict] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        print(f"    XML パース失敗: {exc}", file=sys.stderr)
        return []

    for item in root.findall(".//item")[:num]:
        title_raw = (item.findtext("title") or "").strip()
        # "記事タイトル - Source名" 形式を除去
        title = re.sub(r"\s+-\s+\S.*$", "", title_raw) if " - " in title_raw else title_raw
        link = (item.findtext("link") or "").strip()
        desc_raw = (item.findtext("description") or "").strip()
        desc = re.sub(r"<[^>]+>", "", desc_raw).strip()
        pub_str = item.findtext("pubDate") or ""
        try:
            date_str = parsedate_to_datetime(pub_str).date().isoformat()
        except Exception:
            date_str = datetime.now(timezone.utc).date().isoformat()
        # <source url="..."> から元記事ドメインを取得（Google リダイレクト回避）
        src_elem = item.find("source")
        source_name = src_elem.text.strip() if src_elem is not None else "Unknown"
        source_url = src_elem.get("url", link) if src_elem is not None else link
        items.append({
            "title": title or title_raw,
            "link": link,
            "summary": desc or title_raw,
            "date": date_str,
            "source_name": source_name,
            "source_url": source_url,
        })
    return items


def build_query(entity: dict) -> str:
    """entity の name/vendor から英語クエリを組み立てる。ASCII 部分のみ使用。"""
    eid = entity["entity_id"]
    if eid in QUERY_OVERRIDES:
        return QUERY_OVERRIDES[eid]

    def ascii_words(s: str) -> str:
        return " ".join(w for w in s.split() if all(ord(c) < 128 for c in w))

    name_part = ascii_words(entity.get("name", "")) or eid.replace("-", " ")
    vendor_part = ascii_words(entity.get("vendor", ""))
    return f"{name_part} {vendor_part}".strip()


def _make_event(entity: dict, item: dict, idx: int) -> dict:
    entity_id = entity["entity_id"]
    category = entity["category"]
    event_type = _infer_event_type(item["title"], item["summary"])
    score, importance = _score_and_importance(item["title"], item["source_name"], event_type)
    tier = _source_tier(item["source_url"])
    date = item["date"]
    short = re.sub(r"[^a-z0-9]", "", entity_id.lower())[:8]
    event_id = f"{date}-{short}-rss{idx:02d}"
    return {
        "event_id": event_id,
        "entity_id": entity_id,
        "date": date,
        "category": category,
        "event_type": event_type,
        "headline": item["title"],
        "summary": item["summary"] or item["title"],
        "score": score,
        "importance": importance,
        "source": item["source_name"],
        "source_tier": tier,
        "source_url": item["source_url"],
        "karte_updated": False,
    }


def collect_entities(entity_subset: list[str] | None = None) -> dict:
    """全エンティティ（またはサブセット）の RSS を収集して ingest する。

    返り値: store.ingest_events と同形式 {'added': [...], 'skipped_dup': int, 'skipped_score': int}
    """
    entities, _ = schema.validate_store(DATA / "entities.jsonl", DATA / "events.jsonl")
    targets = {e["entity_id"]: e for e in entities}
    if entity_subset:
        targets = {eid: e for eid, e in targets.items() if eid in entity_subset}

    candidates: list[dict] = []
    for entity_id, entity in targets.items():
        query = build_query(entity)
        print(f"  [{entity_id}] {query!r}")
        items = _fetch_rss(query, num=config.BREAKING_PER_CATEGORY)
        for i, item in enumerate(items, 1):
            try:
                candidates.append(_make_event(entity, item, i))
            except Exception as exc:
                print(f"    スキップ ({entity_id}/{i}): {exc}", file=sys.stderr)
        time.sleep(1.0)  # Google RSS rate limit 対策

    result = store.ingest_events(
        DATA / "entities.jsonl",
        DATA / "events.jsonl",
        candidates,
    )
    print(
        f"RSS 収集完了: 採用 {len(result['added'])} 件 / "
        f"重複スキップ {result['skipped_dup']} 件 / "
        f"閾値スキップ {result['skipped_score']} 件"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    collect_entities(argv if argv else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
