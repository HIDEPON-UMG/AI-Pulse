"""日次速報: News RSS -> 本文 -> ハイブリッド LLM 要約 -> L2 events -> store.ingest_events

依存: 標準ライブラリに加えて google-genai / trafilatura / googlenewsdecoder /
python-dotenv / urllib (Ollama)。
Gemini API キーは AI-Pulse/.env の GEMINI_API_KEY を読む（.env は .gitignore 済み）。
Ollama サーバは localhost:11434 で起動済の前提（HYBRID_MODE=local_first がデフォルト）。
Task Scheduler から run_daily.py 経由で毎日 7:00 に実行。

2026-06-05 (追補11) 本配線:
  抽出 LLM をハイブリッド構成 (Qwen3.6-27B IQ3_XXS → Gemini フォールバック) に切替。同時に
  - rewrite_emphasis: LLM 出力から強調記法 (==/__/**) を決定論で振り直し
  - verify_quant   : summary の数値表現が本文に実在するか照合（捏造数値ゲート）
  を境界に配線。event_id 接尾辞は `-gem<NN>` のまま（互換のため）。
"""
from __future__ import annotations

import html as _html
from collections import Counter
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
import editorial_lint  # noqa: E402
import fetch_article  # noqa: E402
import llm_hybrid  # noqa: E402  # 抽出 LLM のファサード（local / Gemini を可逆切替）
import quality_audit  # noqa: E402
import rewrite_emphasis  # noqa: E402  # 強調記法をコード付与（LLM プロンプトからは強調指示を除去済）
import schema  # noqa: E402
import store  # noqa: E402
import verify_quant  # noqa: E402  # 数値捏造ゲート（summary の数値 vs 本文照合）

DATA = ROOT / "data"

# 旧 QUERY_OVERRIDES dict は entity 側 search_query フィールドへ移行 (2026-06-06)。
# 一般英単語 + 異義語企業 (Runway / Rent the Runway 等) で AI 文脈ゼロの記事が大量混入する
# class of bugs を構造解決するため、検索クエリの単一ソースを entity に集約した
# ([[feedback_check_design_principles]] §1+§2)。本モジュールは build_query() でのみ参照する。

# ドメイン -> source_tier 判定
_T1_DOMAINS = frozenset({
    "anthropic.com", "openai.com", "google.com", "deepmind.com", "googleblog.com",
    "meta.com", "microsoft.com", "nvidia.com", "figureai.com",
    "physicalintelligence.ai", "cognition.ai", "eu.europa.eu",
    "digital.go.jp", "meti.go.jp", "cursor.sh", "cursor.com", "codeium.com",
    "blackforestlabs.ai", "bfl.ai", "runwayml.com", "langchain.com",
    "deepseek.com", "alibabacloud.com", "llama.meta.com",
})
_T2_DOMAINS = frozenset({
    "techcrunch.com", "theverge.com", "wired.com", "reuters.com",
    "bloomberg.com", "wsj.com", "arstechnica.com", "venturebeat.com",
    "thenextweb.com", "zdnet.com", "cnet.com", "tomsguide.com",
    "9to5google.com", "9to5mac.com", "engadget.com", "gizmodo.com",
})

# verify_quant の本文照合に使う数値表現パターン。rewrite_emphasis._NUM_RE を再利用して
# 「強調候補の数値 = 検証対象の数値」を 1 ソースに固定する
# （[[feedback_check_design_principles]] §2）。
_NUM_RE = rewrite_emphasis._NUM_RE
# 半数超が本文に見つからなければ捏造疑いで skip（厳しすぎず緩すぎず・誤検出を抑える）。
_QUANT_MISSING_RATIO_LIMIT = 0.5
# headline_ja 自動翻訳の対象判定: ASCII 比率がこの閾値以上なら「英語見出し」とみなす。
# 0.95 = ほぼ完全英語の見出しのみ翻訳（混在は触らない）。
# 値の根拠: 「Rent The Runway, Perrier Team Up...」のような純英語タイトルだけを拾い、
# 「Qwen 技術リード辞任の舞台裏」のような既に日本語混在の見出しを触らないため。
_HEADLINE_JA_ASCII_THRESHOLD = 0.95


def _ascii_ratio(text: str) -> float:
    """文字列中の ASCII 文字（空白含む）の比率を返す。空文字は 0.0。"""
    if not text:
        return 0.0
    ascii_n = sum(1 for c in text if ord(c) < 128)
    return ascii_n / len(text)


def _needs_headline_ja(headline: str) -> bool:
    """headline が「英語見出し」として翻訳対象か判定。

    判定: ASCII 比率が _HEADLINE_JA_ASCII_THRESHOLD 以上なら True。
    空文字 / 既に日本語混在の見出しは False（= 触らない）。
    """
    return _ascii_ratio(headline) >= _HEADLINE_JA_ASCII_THRESHOLD


def _title_key(entity_id: str, headline: str) -> tuple[str, str] | None:
    """既存 headline と RSS title の重複判定キーを返す。空タイトルは判定しない。"""
    title = re.sub(r"\s+", " ", (headline or "").strip()).casefold()
    if not title:
        return None
    return (entity_id, title)


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
        desc = _html.unescape(re.sub(r"<[^>]+>", "", desc_raw).strip())
        pub_str = item.findtext("pubDate") or ""
        try:
            date_str = parsedate_to_datetime(pub_str).date().isoformat()
        except Exception:
            date_str = datetime.now(timezone.utc).date().isoformat()
        # <source url="..."> から元記事ドメインを取得（fallback 用）
        src_elem = item.find("source")
        source_name = src_elem.text.strip() if src_elem is not None else "Unknown"
        source_url_hint = src_elem.get("url", link) if src_elem is not None else link
        items.append({
            "title": title or title_raw,
            "link": link,
            "rss_summary": desc or title_raw,
            "date": date_str,
            "source_name": source_name,
            "source_url_hint": source_url_hint,
        })
    return items


def build_query(entity: dict) -> str:
    """entity の RSS 検索クエリを 1 経路で決める単一ソース。

    優先順位:
      1. entity.search_query (明示 override) — 一般英単語/異義語企業を持つ entity
         (Runway/Composer/Cosmos など) で AI 文脈に絞るために必須
         ([[feedback_check_design_principles]] §2: 境界 1 箇所集約)。
      2. name + vendor の ASCII 連結 (自動派生) — 固有名修飾で AI 文脈ヒット率が
         実証済の entity (NVIDIA Cosmos / Cursor Composer / Black Forest Flux 等) はこれで十分。

    schema.validate_entity が search_query=非空文字列を保証しているので、ここでは strip 後の
    truthy だけ確認する。
    """
    sq = entity.get("search_query")
    if isinstance(sq, str) and sq.strip():
        return sq.strip()

    def ascii_words(s: str) -> str:
        return " ".join(w for w in s.split() if all(ord(c) < 128 for c in w))

    eid = entity["entity_id"]
    name_part = ascii_words(entity.get("name", "")) or eid.replace("-", " ")
    vendor_part = ascii_words(entity.get("vendor", ""))
    return f"{name_part} {vendor_part}".strip()


def _make_event(entity: dict, item: dict, article: dict, extras: dict, idx: int) -> dict:
    """RSS item + 取得本文 + LLM 出力 から L2 dict を組み立てる。

    article: fetch_article.extract() 返り値（publisher_url / publisher_name / og_image / text）
    extras : llm_hybrid.generate_event_extras() 返り値
        （summary/summary_points/rationale/score/importance/event_type）
    """
    entity_id = entity["entity_id"]
    category = entity["category"]
    publisher_url = article["publisher_url"]
    publisher_name = article.get("publisher_name") or item["source_name"]
    tier = _source_tier(publisher_url)
    date = item["date"]
    short = re.sub(r"[^a-z0-9]", "", entity_id.lower())[:8]
    event_id = f"{date}-{short}-gem{idx:02d}"
    ev = {
        "event_id": event_id,
        "entity_id": entity_id,
        "date": date,
        "category": category,
        "event_type": extras["event_type"],
        "headline": item["title"],
        "summary": extras["summary"],
        "summary_points": extras["summary_points"],
        "rationale": extras["rationale"],
        "score": int(extras["score"]),
        "importance": extras["importance"],
        "source": publisher_name,
        "source_tier": tier,
        "source_url": publisher_url,  # publisher 直リンク（Google News redirect から脱却）
        "karte_updated": False,
    }
    if article.get("og_image"):
        ev["thumb"] = article["og_image"]
    return ev


def _build_meta(entity: dict, item: dict) -> dict:
    return {
        "title": item["title"],
        "entity_name": entity.get("name", ""),
        "category": entity.get("category", ""),
        "vendor": entity.get("vendor", ""),
        "entity_positioning": entity.get("positioning", ""),
    }


def _verify_event_quant(extras: dict, article_text: str) -> tuple[bool, list[str]]:
    """summary / summary_points 内の数値表現が article 本文に存在するか機械照合。

    数値主張がなければ True（検証スキップ）。数値が複数ある場合は「半数超が本文に
    見当たらない」場合のみ False を返す（誤検出抑制のための緩めの閾値）。

    Returns:
        (verified, missing_needles): 採用可否と本文照合できなかった数値リスト
    """
    text_all = (extras.get("summary") or "") + "\n" + "\n".join(extras.get("summary_points") or [])
    numbers = _NUM_RE.findall(text_all)
    if not numbers:
        return True, []
    fetcher = lambda _url: article_text  # noqa: E731 (verify_quant の fetcher 注入用)
    missing: list[str] = []
    for n in numbers:
        result = verify_quant.verify(n, "<article-inline>", fetcher=fetcher)
        if not result["verified"]:
            missing.append(n)
    if missing and len(missing) > len(numbers) * _QUANT_MISSING_RATIO_LIMIT:
        return False, missing
    return True, missing


def collect_entities(entity_subset: list[str] | None = None) -> dict:
    """全エンティティ（またはサブセット）の RSS を収集して ingest する。

    返り値: store.ingest_events と同形式に、本配線で追加した skip カウンタを追記:
      {'added': [...], 'skipped_dup': int, 'skipped_score': int,
       'skipped_pre_dup': int, 'skipped_extract': int, 'skipped_llm': int,
       'skipped_quant': int, 'skipped_validate': int, 'skipped_irrelevant': int,
       'fetch_stage_counts': dict[str, int]}
    """
    entities, existing_events = schema.validate_store(
        DATA / "entities.jsonl",
        DATA / "events.jsonl",
    )
    targets = {e["entity_id"]: e for e in entities}
    if entity_subset:
        targets = {eid: e for eid, e in targets.items() if eid in entity_subset}

    candidates: list[dict] = []
    existing_title_keys = {
        key
        for ev in existing_events
        if (key := _title_key(ev["entity_id"], ev.get("headline", ""))) is not None
    }
    skipped_pre_dup = 0
    skipped_extract = 0
    skipped_llm = 0
    skipped_quant = 0
    skipped_validate = 0
    skipped_irrelevant = 0
    fetch_stage_counts: Counter[str] = Counter()
    audit_records_by_event_id: dict[str, dict] = {}
    known_ids = set(targets) | {e["entity_id"] for e in entities}
    for entity_id, entity in targets.items():
        query = build_query(entity)
        print(f"  [{entity_id}] {query!r}")
        items = _fetch_rss(query, num=config.BREAKING_PER_CATEGORY)
        for i, item in enumerate(items, 1):
            if _title_key(entity_id, item.get("title", "")) in existing_title_keys:
                skipped_pre_dup += 1
                print(
                    f"    skip-predup ({entity_id}/{i}): 既存 headline と同一 title",
                    file=sys.stderr,
                )
                continue
            try:
                article = fetch_article.extract(item["link"])
            except fetch_article.ArticleFetchError as exc:
                skipped_extract += 1
                print(f"    skip-extract ({entity_id}/{i}): {exc}", file=sys.stderr)
                continue
            fetch_stage_counts[article.get("fetch_stage") or "unknown"] += 1
            # 本文を MAX_BODY_CHARS で頭から打切り（追補10: 5000 字までは抽出品質安定）
            article_body = (article["text"] or "")[: config.MAX_BODY_CHARS]
            try:
                extras = llm_hybrid.generate_event_extras(article_body, _build_meta(entity, item))
            except llm_hybrid.LLMError as exc:
                skipped_llm += 1
                print(f"    skip-llm ({entity_id}/{i}): {exc}", file=sys.stderr)
                continue
            # 関連性ゲート（2026-06-07）: 同名異義や entity が主題でない記事を
            # event 化前に弾く。入力側の検索絞り込みで取りこぼす Google News の
            # 緩いマッチを、抽出スキーマの is_relevant で出力側からも封じる。
            # is_relevant=false が明示された時だけ skip し、欠落時は従来通り採用する。
            if not extras.get("is_relevant", True):
                skipped_irrelevant += 1
                reason = extras.get("relevance_reason") or "(理由なし)"
                print(f"    skip-irrelevant ({entity_id}/{i}): {reason}", file=sys.stderr)
                continue
            extras, editorial_findings = editorial_lint.apply_editorial_lint(extras)
            for finding in editorial_findings:
                print(
                    f"    editorial-lint ({entity_id}/{i}): "
                    f"{finding.get('field')} {finding.get('kind')} "
                    f"{finding.get('bad') or finding.get('pattern')} -> "
                    f"{finding.get('good') or finding.get('message')}",
                    file=sys.stderr,
                )
            # 強調記法のコード付与（プロンプトからは強調指示を除去済なので、ここで一括付与）。
            # 新 prompt はプレーンテキスト出力 → add_emphasis_event で数値/動詞/固有名を検出し
            # `==X==` / `__X__` / `**X**` を新規付与する（entity_context で固有名候補を渡す）。
            ev_pre = {"summary": extras["summary"], "summary_points": extras["summary_points"]}
            ev_marked, _ = rewrite_emphasis.add_emphasis_event(ev_pre, entity_context=entity)
            # レガシー entry 由来の `**X**` が残っていた場合の保険（冪等）
            ev_rewritten, _ = rewrite_emphasis.rewrite_event(ev_marked)
            extras["summary"] = ev_rewritten["summary"]
            extras["summary_points"] = ev_rewritten["summary_points"]
            # 数値捏造ゲート（本文と機械照合）
            verified, missing = _verify_event_quant(extras, article_body)
            if not verified:
                skipped_quant += 1
                print(
                    f"    skip-quant ({entity_id}/{i}): 数値 {missing!r} が本文照合不可",
                    file=sys.stderr,
                )
                continue
            try:
                ev = _make_event(entity, item, article, extras, i)
                # 2026-06-05 (追補13): 英語見出し（ASCII 比率 _HEADLINE_JA_ASCII_THRESHOLD 以上）
                # なら headline_ja を翻訳付与。UI (index.html.j2 / app.js initDigest) は
                # headline_ja があれば優先表示し、長い英語 h1 が CSS line-clamp 3 で
                # 切れる事故を防ぐ。翻訳失敗は warn のみ・headline_ja 無しで通す。
                if _needs_headline_ja(ev["headline"]):
                    try:
                        # entity_context=None 固定。entity dict を渡すと LLM プロンプトに
                        # 「固有名詞ヒント: <name>, <vendor>」が注入され、headline に登場しない
                        # entity 名まで翻訳に強制注入される事故が出る (Part 6 flux 捏造事例)。
                        # apply_headline_ja / regenerate_rationale と契約を統一する
                        # ([[feedback_check_design_principles]] §2 境界 1 箇所集約)。
                        ev["headline_ja"] = llm_hybrid.translate_headline_ja(
                            ev["headline"], entity_context=None
                        )
                    except llm_hybrid.LLMError as exc:
                        print(
                            f"    skip-headline-ja ({entity_id}/{i}): {exc}",
                            file=sys.stderr,
                        )
                schema.validate_event(ev, known_ids)
            except schema.SchemaError as exc:
                skipped_validate += 1
                print(f"    skip-validate ({entity_id}/{i}): {exc}", file=sys.stderr)
                continue
            candidates.append(ev)
            audit_record = quality_audit.build_audit_record(ev, article_body)
            audit_record["fetch_stage"] = article.get("fetch_stage") or "unknown"
            audit_records_by_event_id[ev["event_id"]] = audit_record
        time.sleep(1.0)  # Google RSS rate limit 対策

    result = store.ingest_events(
        DATA / "entities.jsonl",
        DATA / "events.jsonl",
        candidates,
    )
    result["skipped_extract"] = skipped_extract
    result["skipped_pre_dup"] = skipped_pre_dup
    result["skipped_llm"] = skipped_llm
    result["skipped_quant"] = skipped_quant
    result["skipped_validate"] = skipped_validate
    result["skipped_irrelevant"] = skipped_irrelevant
    result["fetch_stage_counts"] = dict(fetch_stage_counts)
    result["quality_audit_records"] = [
        audit_records_by_event_id[ev["event_id"]]
        for ev in result["added"]
        if ev["event_id"] in audit_records_by_event_id
    ]
    print(
        f"RSS+ハイブリッド LLM 収集完了: 採用 {len(result['added'])} 件 / "
        f"pre重複 {skipped_pre_dup} / 重複 {result['skipped_dup']} / "
        f"閾値 {result['skipped_score']} / "
        f"本文NG {skipped_extract} / LLM失敗 {skipped_llm} / 数値NG {skipped_quant} / "
        f"無関係 {skipped_irrelevant} / schema違反 {skipped_validate} / "
        f"取得段 {dict(fetch_stage_counts)}"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    collect_entities(argv if argv else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
