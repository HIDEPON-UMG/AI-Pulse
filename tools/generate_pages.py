"""AI-Pulse 静的サイトジェネレータ（SSG）。

``schema.validate_store`` で検証済みの L1 カルテ / L2 デルタを Jinja2 テンプレへ流し込み、
``site/`` に index（フィード）・archive（タイムライン）・karte-<id>（分析カルテ）を生成する。

決定論変換（カテゴリ→色/グリフ、importance/ripple/score→3 指標、相対日付、カルテ整形）は
本モジュールに**集約**する。LLM はここでは一切使わない（収集・要約・抽出は別ジョブの責務）。
分担原則: LLM=分類/下書き/要約/抽出、コード=ルーティング/閾値/決定論変換。
"""
from __future__ import annotations

import datetime as dt
import re
import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup, escape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tools/ を import path に載せる
import config  # noqa: E402
import schema  # noqa: E402

TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "site"

# 出力へコピーするアセット拡張子（HTML は描画物なのでコピーしない）
ASSET_SUFFIXES = {".css", ".js", ".svg", ".webmanifest", ".json", ".png", ".ico"}

# --- 表示メタ（schema の enum と 1:1 対応させる。未知値は KeyError で気付ける） ---
CAT_META = {
    "model": {"label": "モデル/LLM", "glyph": "◆"},
    "editor": {"label": "AIエディタ・コーディング", "glyph": "▲"},
    "media": {"label": "画像・動画・音声生成", "glyph": "◎"},
    "agent": {"label": "エージェント・ツール", "glyph": "■"},
    "infra": {"label": "インフラ・チップ", "glyph": "▶"},
    "policy": {"label": "規制・資金・業界", "glyph": "✦"},
    "physical": {"label": "フィジカルAI", "glyph": "⬢"},
}
TIER_LABEL = {"T1": "T1 公式", "T2": "T2 一次報道", "T3": "T3 二次"}
KIND_JA = {
    "model": "モデル", "runtime": "ランタイム", "app": "アプリ",
    "library": "ライブラリ", "repo": "リポジトリ",
    "hardware": "ハードウェア", "regulation": "規制/政策",
}
OFFERING_JA = {"oss": "OSS", "saas": "SaaS", "commercial": "商用",
               "hybrid": "ハイブリッド", "public": "公的"}
DOMAIN_JA = {
    "language": "言語", "code": "コード", "image": "画像",
    "video": "動画", "audio": "音声", "multimodal": "マルチモーダル",
    "robotics": "ロボティクス", "compute": "計算基盤", "governance": "ガバナンス",
    "agent": "エージェント",
}
# 企業間関係 type → (CSS クラス, ラベル, 矢印)。未知 type は REL_FALLBACK。
REL_META = {
    "capital": ("rc-capital", "資本", "←"),
    "tech_dependency": ("rc-tech", "技術依存", "←"),
    "api_supply": ("rc-tech", "API供給", "←"),
    "rival": ("rc-rival", "競合", "↔"),
    "standard": ("rc-std", "標準化協調", "↔"),
    "std": ("rc-std", "標準化協調", "↔"),
}
REL_FALLBACK = ("rc-tech", "関係", "→")
# 採用判断マーク → CSS クラス
REC_CLS = {"◎": "dbl", "○": "cir", "△": "tri", "×": "tri"}
WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]
DOW_EN = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def _level(flag: str) -> str:
    """importance(high/mid/low) → CSS の data-level(高/中/低)。"""
    return {"high": "高", "mid": "中", "low": "低"}.get(flag, "低")


def _impact_level(ripple) -> str:
    """影響度: 波及主体(ripple)の数から決定論導出（2+→高 / 1→中 / 0→低）。"""
    n = len(ripple or [])
    return "高" if n >= 2 else ("中" if n == 1 else "低")


def _buzz_level(score: int) -> str:
    """話題性: ニュース性スコアの帯から決定論導出（80+→高 / 60+→中 / それ未満→低）。"""
    return "高" if score >= 80 else ("中" if score >= 60 else "低")


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _rel_label(ref: dt.date, d: dt.date) -> str:
    """最新ニュース日(ref)を「本日」基準にした相対表記。"""
    days = (ref - d).days
    return "本日" if days <= 0 else f"{days}日前"


def _clean_summary(summary: str, headline: str) -> str:
    """RSS OGP 由来の要約を整形して返す。
    HTMLエンティティをデコード後、  出典名サフィックスを除去。
    headline と実質同一なら空文字を返す。"""
    import html as _html
    if not summary:
        return ""
    # &nbsp; 等の HTML エンティティを Unicode に正規化（&nbsp; →  ）
    s = _html.unescape(summary.strip())
    # "タイトル  出典名" 形式の出典名サフィックスを除去
    core = re.sub(r" .*$", "", s).strip()
    if not core:
        return ""
    # core が headline と完全一致なら要約として価値なし
    if core.strip().lower() == headline.strip().lower():
        return ""
    return core


def _auto_rationale(ev: dict) -> dict:
    """rationale が無い RSS イベント向けにスコア・重要度・波及から簡易根拠テキストを生成する。"""
    imp = _level(ev.get("importance", "low"))
    n_ripple = len(ev.get("ripple") or [])
    imp_label = {"高": "high", "中": "mid", "低": "low"}.get(imp, "low")
    return {
        "importance": f"スコア{ev['score']}・{imp}水準の報道（{ev.get('source','不明')}）",
        "impact": f"波及先{n_ripple}件 → {'高' if n_ripple >= 2 else '中' if n_ripple == 1 else '低'}水準",
        "buzz": f"ニュース性スコア{ev['score']}（{'80+ 高' if ev['score'] >= 80 else '60+ 中' if ev['score'] >= 60 else '60未満 低'}）",
    }


def _story(ev: dict, ent_by_id: dict, ref: dt.date, *, feature: bool) -> dict:
    cat = ev["category"]
    d = _d(ev["date"])
    ent = ent_by_id.get(ev["entity_id"])
    rat = ev.get("rationale") or {}
    if not rat:
        rat = _auto_rationale(ev)
    summary = _clean_summary(ev.get("summary", ""), ev["headline"])
    return {
        "id": ev["event_id"],
        "cat": cat,
        "cat_label": CAT_META[cat]["label"],
        "glyph": CAT_META[cat]["glyph"],
        "score": ev["score"],
        "headline": ev["headline"],
        "summary": summary,
        "source": ev["source"],
        "tier": ev["source_tier"],
        "tier_label": TIER_LABEL.get(ev["source_tier"], ev["source_tier"]),
        "date_md": d.strftime("%m-%d"),
        "date_rel": _rel_label(ref, d),
        "importance": _level(ev["importance"]),
        "impact": _impact_level(ev.get("ripple")),
        "buzz": _buzz_level(ev["score"]),
        "karte": f"karte-{ev['entity_id']}.html" if ent else None,
        "source_url": ev.get("source_url"),
        "summary_points": ev.get("summary_points") or [],
        "rationale": rat,
        "karte_updated": bool(ev.get("karte_updated")),
        "thumb": ev.get("thumb") or "",
        "feature": feature,
    }


def _karte(ent: dict, all_events: list[dict]) -> dict:
    cat = ent["category"]
    conf = ent.get("confidence") or {}
    total = sum(v for v in conf.values() if isinstance(v, int))
    conf_pct = round(conf.get("asserted", 0) / total * 100) if total else 0
    rels = []
    for r in ent.get("relations") or []:
        cls, label, arr = REL_META.get(r.get("type"), REL_FALLBACK)
        rels.append({
            "company": r.get("company", ""), "note": r.get("note", ""),
            "cls": cls, "label": label, "arr": arr,
            "since": r.get("since", ""), "models": r.get("models") or [],
            "url": r.get("url", ""),
        })
    rec = ent.get("recommendation") or {}
    rec_rows = [
        {"scene": "個人開発", "mark": rec.get("individual", "—")},
        {"scene": "業務(小規模)", "mark": rec.get("business", "—")},
        {"scene": "クライアント提案", "mark": rec.get("client", "—")},
    ]
    for row in rec_rows:
        row["cls"] = REC_CLS.get(row["mark"], "tri")
    # backlink: この entity を参照する最新デルタの出典（新しい順・重複排除）
    ent_events = [e for e in all_events if e["entity_id"] == ent["entity_id"]]
    ent_events = ent_events[: config.RECENT_EVENTS_CAP]
    seen: set = set()
    sources = []
    for e in ent_events:
        key = (e["source"], e["source_tier"])
        if key not in seen:
            seen.add(key)
            sources.append({"source": e["source"], "tier": e["source_tier"]})
    modules = ent.get("modules") or {}
    # 比較軸はレンズ共通（schema.LENS_AXES が単一ソース）。entity は cols だけ持つ。
    cmp = ent.get("comparison")
    comparison = ({"axes": schema.LENS_AXES.get(cat, []), "cols": cmp["cols"]}
                  if cmp and cmp.get("cols") else None)
    return {
        "id": ent["entity_id"], "name": ent["name"], "cat": cat,
        "cat_label": CAT_META[cat]["label"], "glyph": CAT_META[cat]["glyph"],
        "positioning": ent["positioning"], "vendor": ent["vendor"],
        "kind_ja": KIND_JA.get(ent["kind"], ent["kind"]),
        "domain_ja": DOMAIN_JA.get(ent["domain"], ent["domain"]),
        "offering_ja": OFFERING_JA.get(ent["offering"], ent["offering"]),
        "conf_pct": conf_pct,
        "competitors": ent.get("competitors") or [],
        "relations": rels,
        "rec_rows": rec_rows,
        "sources": sources,
        # 裏付けデータがある時だけ描画（無ければテンプレ側 {% if %} で非表示・捏造しない）
        "history": ent.get("history") or [],
        "comparison": comparison,
        "future": modules.get("future") or [],
        "overview": ent.get("overview") or None,
    }


def build_context(entities: list[dict], events: list[dict]) -> dict:
    """検証済み L1/L2 から全テンプレ用の文脈を組む（決定論変換の集約点）。"""
    ent_by_id = {e["entity_id"]: e for e in entities}
    ref = max((_d(e["date"]) for e in events), default=dt.date.today())
    all_events = sorted(events, key=lambda e: (e["date"], e["event_id"]), reverse=True)
    feed_events = [e for e in all_events if e["score"] >= config.SCORE_MIN]

    feed = [_story(ev, ent_by_id, ref, feature=(i == 0)) for i, ev in enumerate(feed_events)]

    groups: list[dict] = []
    for ev in all_events:
        d = _d(ev["date"])
        if not groups or groups[-1]["date"] != ev["date"]:
            groups.append({
                "date": ev["date"], "day": d.strftime("%d"), "ym": d.strftime("%Y.%m"),
                "dow": DOW_EN[d.weekday()], "cat": ev["category"], "score": ev["score"],
                "entries": [],
            })
        ent = ent_by_id.get(ev["entity_id"])
        groups[-1]["entries"].append({
            "cat": ev["category"], "cat_label": CAT_META[ev["category"]]["label"],
            "glyph": CAT_META[ev["category"]]["glyph"], "headline": ev["headline"],
            "source": ev["source"], "tier": ev["source_tier"],
            "tier_label": TIER_LABEL.get(ev["source_tier"], ev["source_tier"]),
            "score": ev["score"],  # スコアは各記事タイル右端に表示（日付レールと混同しないため）
            "karte": f"karte-{ev['entity_id']}.html" if ent else None,
        })

    if all_events:
        dmax, dmin = _d(all_events[0]["date"]), _d(all_events[-1]["date"])
        range_label = (
            f"{dmax.year}年{dmax.month}月 — {dmin.month}月"
            if (dmax.year, dmax.month) != (dmin.year, dmin.month)
            else f"{dmax.year}年{dmax.month}月"
        )
    else:
        range_label = ""

    return {
        "feed": feed, "feed_count": len(feed),
        "groups": groups, "archive_count": len(all_events), "range_label": range_label,
        "kartes": [_karte(ent, all_events) for ent in entities],
        "ref_date_label": f"{ref.isoformat()} ({WEEKDAY_JA[ref.weekday()]})",
        "build": ref.isoformat(),
    }


def _copy_assets() -> int:
    n = 0
    for f in sorted(STATIC_DIR.iterdir()):
        if f.is_file() and f.suffix in ASSET_SUFFIXES:
            shutil.copy2(f, OUT_DIR / f.name)
            n += 1
    return n


# News-Grasp 流の軽量強調記法（**太字** / __下線__ / ==マーカー==）。
# 適用順は外側の長い記法から。`escape` 済みテキストにだけ置換するため XSS 不可。
_EMPH_RULES = (
    (re.compile(r"==(.+?)=="), r"<mark>\1</mark>"),
    (re.compile(r"\*\*(.+?)\*\*"), r"<b>\1</b>"),
    (re.compile(r"__(.+?)__"), r"<u>\1</u>"),
)


def emph(text: str) -> Markup:
    """本文の軽量強調記法を安全な HTML に変換する Jinja フィルタ。

    先に HTML エスケープしてから記法→タグへ置換するので、データ側に < や " が
    混入しても無害（autoescape と同じ安全性を保ちつつ強調だけ通す）。記法が無ければ
    エスケープ済みプレーン文字列をそのまま返す。
    """
    if not text:
        return Markup("")
    s = str(escape(text))
    for rx, rep in _EMPH_RULES:
        s = rx.sub(rep, s)
    return Markup(s)


def make_env() -> Environment:
    """全テンプレ共通の Jinja 環境。autoescape=True で値を自動エスケープし、
    <script> へ値を出す時だけ |tojson を使う（XSS / JSON 破損を 1 箇所で封じる）。
    本文の軽量強調は `emph` フィルタが escape→記法置換の順で安全に通す。"""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["emph"] = emph
    return env


def generate(out_dir: Path = OUT_DIR) -> dict:
    """site/ を生成して概要 dict を返す（テストはこの戻り値と出力ファイルを検査する）。"""
    entities, events = schema.validate_store(
        DATA_DIR / "entities.jsonl", DATA_DIR / "events.jsonl"
    )
    ctx = build_context(entities, events)
    env = make_env()
    out_dir.mkdir(parents=True, exist_ok=True)
    assets = _copy_assets() if out_dir == OUT_DIR else 0
    pages = []
    (out_dir / "index.html").write_text(
        env.get_template("index.html.j2").render(**ctx, page="feed"), encoding="utf-8"
    )
    pages.append("index.html")
    (out_dir / "archive.html").write_text(
        env.get_template("archive.html.j2").render(**ctx, page="archive"), encoding="utf-8"
    )
    pages.append("archive.html")
    karte_tpl = env.get_template("karte.html.j2")
    for k in ctx["kartes"]:
        name = f"karte-{k['id']}.html"
        (out_dir / name).write_text(karte_tpl.render(**ctx, page="karte", k=k), encoding="utf-8")
        pages.append(name)
    return {
        "pages": pages, "assets": assets,
        "feed": ctx["feed_count"], "archive": ctx["archive_count"], "kartes": len(ctx["kartes"]),
    }


def main() -> None:
    r = generate()
    n = len(r["pages"])
    detail = f"feed {r['feed']} / archive {r['archive']} / karte {r['kartes']}"
    print(f"[generate_pages] site/ に {n} ページ生成（{detail}、asset {r['assets']} 件コピー）")


if __name__ == "__main__":
    main()
