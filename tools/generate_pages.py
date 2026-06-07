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


def _human_rel(ref: dt.date, d: dt.date) -> str:
    """カルテ一覧の「直近アップデート」用に、一目で経過時間が分かる粗い相対表記。
    本日 / 昨日 / N日前 / 先週 / N週間前 / 先月 / Nヶ月前 / N年前 の段階表現。"""
    days = (ref - d).days
    if days <= 0:
        return "本日更新"
    if days == 1:
        return "昨日"
    if days < 7:
        return f"{days} 日前"
    if days < 14:
        return "先週"
    if days < 30:
        return f"{days // 7} 週間前"
    if days < 60:
        return "先月"
    if days < 365:
        return f"{days // 30} ヶ月前"
    return f"{days // 365} 年前"


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


def _karte_fit_metrics(name: str, container_px: int = 198, base_px: int = 22, min_px: int = 11) -> dict:
    """カルテ名 `name` がサムネ列 `container_px` に収まる font-size と padding を返す。

    トップフィードのサムネ列は 200px 固定。カルテ chip は white-space:nowrap のため、
    base 22px のままだと "Physical Intelligence" (21 字) のような長文 ASCII カルテ名が
    サムネ画像の右端を超えて溢れる。境界 1 箇所 (本関数) で chip 寸法を逆算し、テンプレに
    インライン style で渡すことで物理的に封じる ([feedback_check_design_principles] §2)。

    chip 全幅 ≈ fs × (chars_em + padding_em_total) + border
      - chars_em: ASCII=0.6em / CJK=1.0em (mono font 想定)
      - padding_em_total: base 17px@22px = 0.773em の左右合計 ≈ 1.546em
      - border: 1px × 2 = 2px (固定)
    max fs = (container_px - border) / (chars_em + padding_em_total)
    fs は base_px 〜 min_px でクランプ。padding は fs に比例 (round 整数)。
    """
    if not name:
        return {"font_size": base_px, "py": 9, "px": 17}
    chars_em = sum(1.0 if ord(c) > 0x7F else 0.6 for c in name)
    padding_em_total = 17 * 2 / base_px  # ≈ 1.545
    border = 2
    max_fs = (container_px - border) / (chars_em + padding_em_total)
    fs = int(min(base_px, max(min_px, max_fs)))
    r = fs / base_px
    py = max(5, round(9 * r))
    px = max(8, round(17 * r))
    return {"font_size": fs, "py": py, "px": px}


def _karte_names(ev: dict, ent_by_id: dict) -> list[dict]:
    """主 entity と related_entities を解決して [{name, href, font_size, py, px}, ...] の順序付きリストを返す。

    主カルテを先頭・関連カルテをデータ記載順に並べる。entity_id が L1 に無い場合はスキップ。
    related_entities の参照整合は schema 側で担保済み（known_entity_ids チェック）。
    font_size/py/px は _karte_fit_metrics でカルテ名長に応じて自動縮小 (サムネ列 200px に収める)。
    """
    items: list[dict] = []
    primary = ent_by_id.get(ev["entity_id"])
    if primary:
        items.append({"name": primary["name"], "href": f"karte-{ev['entity_id']}.html", **_karte_fit_metrics(primary["name"])})
    for rid in ev.get("related_entities") or []:
        ent = ent_by_id.get(rid)
        if ent:
            items.append({"name": ent["name"], "href": f"karte-{rid}.html", **_karte_fit_metrics(ent["name"])})
    return items


def _summary_short(ev: dict) -> str:
    """アーカイブの1行サマリ用に summary を 60字目安で切り詰める。

    タイムラインは情報密度を保つため short 表示。空 / headline と同義なら空文字を返し
    テンプレ側で {% if %} 非表示にする（捏造表示の防止）。

    強調記法（** / == / __）は切り詰めで閉じない記号が残ると壊れて見えるため、
    archive では先に全削除して plain にする（フィード本文だけが強調記法の対象）。
    """
    s = _clean_summary(ev.get("summary", ""), ev["headline"])
    if not s:
        return ""
    # 強調記法を plain 化（archive は密圧縮で意味分けの恩恵が薄く、切り詰めで記号残りを防ぐ）
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"==([^=]+)==", r"\1", s)
    s = re.sub(r"__([^_]+)__", r"\1", s)
    if len(s) > 60:
        s = s[:58].rstrip() + "…"
    return s


def _plain_summary_text(text: str) -> str:
    """表示見出し候補に使う文章を plain text に寄せる。"""
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text or "")
    text = re.sub(r"==([^=]+)==", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    return re.sub(r"\s+", " ", text).strip().strip("。")


def _display_headline(ev: dict) -> str:
    """省略しない表示用タイトル。

    元見出しや直訳 headline_ja が長い場合でも、カード用の 1 行目は要約済みの
    summary_points[0] / summary から採る。末尾の「…」は付けず、切り詰め表示に見せない。
    """
    for point in ev.get("summary_points") or []:
        s = _plain_summary_text(point)
        if s:
            return s
    summary = _clean_summary(ev.get("summary", ""), ev["headline"])
    if summary:
        # summary は 1 文目をタイトル扱いにする。句点が無い場合は全文を使う。
        first = re.split(r"[。！？]", _plain_summary_text(summary), maxsplit=1)[0].strip()
        if first:
            return first
    return (ev.get("headline_ja") or ev["headline"]).strip()


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
        "headline_ja": ev.get("headline_ja") or "",
        "display_headline": _display_headline(ev),
        "ent_name": ent["name"] if ent else "",
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
        "karte_names": _karte_names(ev, ent_by_id),
        "source_url": ev.get("source_url"),
        "summary_points": ev.get("summary_points") or [],
        "rationale": rat,
        "karte_updated": bool(ev.get("karte_updated")),
        "thumb": ev.get("thumb") or "",
        "feature": feature,
    }


def _karte(ent: dict, all_events: list[dict], ent_by_id: dict, ref: dt.date) -> dict:
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
    # 関連ニュース: 主 entity_id 一致 + related_entities にこの entity_id が含まれるイベント全件
    # （SCORE_MIN フィルタは外す。カルテはアーカイブ的役割も持つため）。all_events は既に
    # 新しい順ソート済みなので filter のみで時系列順を維持する。
    feed_items = [
        _story(ev, ent_by_id, ref, feature=False)
        for ev in all_events
        if ev["entity_id"] == ent["entity_id"]
        or ent["entity_id"] in (ev.get("related_entities") or [])
    ]
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
        "feed_items": feed_items,
    }


def build_context(entities: list[dict], events: list[dict], *, build_date: dt.date | None = None) -> dict:
    """検証済み L1/L2 から全テンプレ用の文脈を組む（決定論変換の集約点）。

    フィードは「events 全体の最大 date と一致するデルタ」だけを表示する（=最新記事日）。
    サイトの更新表示は生成実行日に合わせる。ユーザー要件 2026-06-08。
    """
    ent_by_id = {e["entity_id"]: e for e in entities}
    ref = build_date or dt.date.today()
    latest_event_date = max((_d(e["date"]) for e in events), default=ref)
    latest_event_iso = latest_event_date.isoformat()
    all_events = sorted(events, key=lambda e: (e["date"], e["event_id"]), reverse=True)
    feed_events = [e for e in all_events if e["score"] >= config.SCORE_MIN]
    feed_today_events = [e for e in feed_events if e["date"] == latest_event_iso]
    feed = [_story(ev, ent_by_id, ref, feature=(i == 0))
            for i, ev in enumerate(feed_today_events)]

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
            "headline_ja": ev.get("headline_ja") or "",
            "display_headline": _display_headline(ev),
            "source": ev["source"], "tier": ev["source_tier"],
            "tier_label": TIER_LABEL.get(ev["source_tier"], ev["source_tier"]),
            "score": ev["score"],  # スコアは各記事タイル右端に表示（日付レールと混同しないため）
            "karte": f"karte-{ev['entity_id']}.html" if ent else None,
            "karte_names": _karte_names(ev, ent_by_id),  # 実カルテ名（複数対応）
            "summary_short": _summary_short(ev),         # 英文タイトル対策の1行サマリ
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

    # カルテごとの「直近更新日」: そのカルテに紐づく events(主 entity_id + related_entities)の最大 date。
    # related_entities まで取るのは、複数カルテ紐づきイベントを「全関連カルテで更新扱い」にするため。
    latest_by_entity: dict[str, dt.date] = {}
    for ev in all_events:
        d = _d(ev["date"])
        ids = [ev["entity_id"]] + list(ev.get("related_entities") or [])
        for eid in ids:
            if eid not in latest_by_entity or d > latest_by_entity[eid]:
                latest_by_entity[eid] = d

    # カルテ一覧（カテゴリ別カード）。CAT_META の宣言順をレンズ並びの単一ソースとして使う。
    # 名前は `cards` を使う（Jinja2 で `g.items` は dict.items メソッドと衝突するため）。
    # 並び順: 直近アップデートが新しい順（同日内は名前昇順）。「動いている」カルテを上に出す。
    karte_index_groups: list[dict] = []
    for cat in CAT_META:
        cards = sorted(
            [
                # feed_* = フィード(events 最新)由来 / karte_* = カルテ本体(entity.snapshot_date)由来。
                # 2 種を別バッジで並列表示し「何が更新されたか」を一目で示す (2026-06-04)。
                {
                    "id": e["entity_id"], "name": e["name"], "cat": cat,
                    "cat_label": CAT_META[cat]["label"], "glyph": CAT_META[cat]["glyph"],
                    "positioning": e["positioning"], "vendor": e["vendor"],
                    "href": f"karte-{e['entity_id']}.html",
                    "feed_updated_rel": (_human_rel(ref, latest_by_entity[e["entity_id"]])
                                         if e["entity_id"] in latest_by_entity else None),
                    "feed_updated_abs": (latest_by_entity[e["entity_id"]].isoformat()
                                         if e["entity_id"] in latest_by_entity else None),
                    "feed_updated_fresh": (e["entity_id"] in latest_by_entity and
                                           (ref - latest_by_entity[e["entity_id"]]).days <= 7),
                    "karte_updated_rel": _human_rel(ref, _d(e["snapshot_date"])),
                    "karte_updated_abs": e["snapshot_date"],
                    "karte_updated_fresh": (ref - _d(e["snapshot_date"])).days <= 7,
                }
                for e in entities if e["category"] == cat
            ],
            key=lambda x: (
                # 最新日が新しい順 (None は最後尾)
                -(latest_by_entity[x["id"]].toordinal()
                  if x["id"] in latest_by_entity else 0),
                x["name"].lower(),
            ),
        )
        if cards:
            karte_index_groups.append({
                "cat": cat, "cat_label": CAT_META[cat]["label"],
                "glyph": CAT_META[cat]["glyph"], "cards": cards,
            })

    return {
        "feed": feed, "feed_count": len(feed),
        "feed_total_published": len(feed_events),  # 当日以外も含む全 published（参考表示）
        "groups": groups, "archive_count": len(all_events), "range_label": range_label,
        "kartes": [_karte(ent, all_events, ent_by_id, ref) for ent in entities],
        "karte_index_groups": karte_index_groups,
        "karte_total": len(entities),
        "ref_date_label": f"{ref.isoformat()} ({WEEKDAY_JA[ref.weekday()]})",
        "build": ref.isoformat(),
        "site_url": config.SITE_URL,  # OGP 絶対 URL の組立に使う（_head.html.j2）
    }


def _copy_assets(out_dir: Path) -> int:
    """static/ 配下のホワイトリスト拡張子をすべて `out_dir` に流す。

    本番 (OUT_DIR) でも tmp ディレクトリでも同じ経路を辿るよう out_dir を引数化した
    （2026-06-05 改修: テストが OGP png 等のアセット貫通を検証できるようにするため）。
    """
    n = 0
    for f in sorted(STATIC_DIR.iterdir()):
        if f.is_file() and f.suffix in ASSET_SUFFIXES:
            shutil.copy2(f, out_dir / f.name)
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
    assets = _copy_assets(out_dir)
    pages = []
    (out_dir / "index.html").write_text(
        env.get_template("index.html.j2").render(**ctx, page="feed"), encoding="utf-8"
    )
    pages.append("index.html")
    (out_dir / "archive.html").write_text(
        env.get_template("archive.html.j2").render(**ctx, page="archive"), encoding="utf-8"
    )
    pages.append("archive.html")
    (out_dir / "karte-index.html").write_text(
        env.get_template("karte-index.html.j2").render(**ctx, page="karte_index"),
        encoding="utf-8",
    )
    pages.append("karte-index.html")
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
