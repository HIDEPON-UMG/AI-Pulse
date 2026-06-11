"""AI-Pulse データモデル: L1 エンティティ・カルテ / L2 イベント・デルタ。

設計方針:
- スキーマ検証は本モジュールの ``validate_*`` に**集約**する（境界 1 箇所）。
  上位コード（収集・SSG）は ``validate_store`` を通った検証済みデータだけを扱い、
  個別箇所でフィールド存在チェックを散らさない。
- 許容値は集合（CATEGORIES 等）で表現し、未知値は弾く＝不正状態を持ち回らせない。
- L2 デルタは ``entity_id`` で L1 カルテを参照する。参照が解決することを不変条件とする。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

# JS 文字列リテラル / HTML 属性 / URL 構文を破壊しうる危険文字。
# templates/index.html.j2 が source_url を JS の onclick 文字列に埋め込むため、
# ' を含む URL を許すと DOM XSS の経路になる（Jinja autoescape は JS 文字列のクオートをエスケープしない）。
# → ingest 時点で illegal state を表現できないようにする（feedback_check_design_principles §1）
_URL_FORBIDDEN_CHARS = frozenset("'\"<>\n\r\t\x00\\`")

# --- 許容値（enum 相当。ここに無い値は validate_* が弾く） ---
CATEGORIES = {"model", "editor", "media", "agent", "infra", "policy", "physical"}  # 7 レンズ
KINDS = {"model", "runtime", "app", "library", "repo", "hardware", "regulation"}
# hardware=チップ/インフラ(infra レンズ), regulation=規制/政策(policy レンズ)。7レンズ化に伴う追加。
OFFERINGS = {"oss", "saas", "commercial", "hybrid", "public"}
# public=公的（規制・法令など「提供」概念が当てはまらない policy レンズ向け）。
EVENT_TYPES = {"release", "funding", "pricing", "ma", "shutdown", "incident", "benchmark", "regulation"}
# regulation=規制の施行・ガイドライン公表など(policy レンズ)。
SOURCE_TIERS = {"T1", "T2", "T3"}  # T1 公式/一次, T2 一次報道, T3 二次/個人
IMPORTANCE = {"high", "mid", "low"}
LOGO_STATUSES = {"verified", "candidate", "missing"}

# rationale 各値の最低文字数。prompt は 40〜80 字を要求しているが、安全側で 20 字以上を
# 「文章として最低限の情報量」のハードゲートにする。これ以下は "high"/"mid"/"low" や
# 「高と判定」等のラベル反復とみなして弾く ([[feedback_check_design_principles]] §1:
# illegal state を表現できなくする / §4: 契約テスト 1 件で不変条件を locked-in)。
_RATIONALE_MIN_LEN = 20

ENTITY_REQUIRED = (
    "entity_id", "name", "kind", "domain", "offering", "vendor",
    "category", "snapshot_date", "positioning",
)
# オプション項目: あれば形を固定する（無い entity はテンプレ側 {% if %} で非表示）。
# history = テクニカル・ヒストリー。新しい順（先頭=最新 now=true）で記述。
#          各項目 when/title 必須。note / source / url（http）は任意。
# comparison = 競合比較マトリクス。比較軸はレンズ(category)共通（LENS_AXES が単一ソース）。
#          entity は cols(name/cells) だけ持つ。各 col は所属レンズ全 axis キーのセルを揃える。
HISTORY_ITEM_REQUIRED = ("when", "title")
LOGO_PATH_PREFIX = "assets/service-icons/"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# レンズ(7カテゴリ)ごとの比較軸。「同レンズ=同軸」を強制する単一ソース（方針B）。
# entity.comparison.cols の cells はここで定義した key を全て埋める。
LENS_AXES = {
    "model": [
        {"key": "strength", "label": "主な強み"},
        {"key": "context", "label": "コンテキスト長"},
        {"key": "mm_in", "label": "マルチモーダル(入力)"},
        {"key": "mm_out", "label": "マルチモーダル(出力)"},
        {"key": "ecosystem", "label": "拡張・連携"},
        {"key": "pricing", "label": "価格(API/サービス)"},
    ],
    "editor": [
        {"key": "iface", "label": "インターフェース"},
        {"key": "auto", "label": "エージェント自律度"},
        {"key": "strength", "label": "主な強み"},
        {"key": "mcp", "label": "拡張(MCP)"},
        {"key": "pricing", "label": "価格モデル"},
    ],
    "media": [
        {"key": "offering", "label": "提供形態"}, {"key": "strength", "label": "主な強み"},
        {"key": "control", "label": "制御性"}, {"key": "video", "label": "動画対応"},
        {"key": "license", "label": "ライセンス"},
    ],
    "agent": [
        {"key": "autonomy", "label": "自律度"}, {"key": "tools", "label": "ツール連携"},
        {"key": "strength", "label": "主な強み"}, {"key": "extensibility", "label": "拡張性"},
        {"key": "pricing", "label": "価格モデル"},
    ],
    "infra": [
        {"key": "offering", "label": "提供形態"}, {"key": "scale", "label": "スケール"},
        {"key": "strength", "label": "主な強み"}, {"key": "integration", "label": "連携"},
        {"key": "pricing", "label": "価格モデル"},
    ],
    "policy": [
        {"key": "scope", "label": "適用範囲"}, {"key": "binding", "label": "拘束力"},
        {"key": "topic", "label": "主な論点"}, {"key": "target", "label": "対象"},
        {"key": "timing", "label": "施行時期"},
    ],
    "physical": [
        {"key": "form", "label": "形態"}, {"key": "hardware", "label": "対応ハード"},
        {"key": "foundation", "label": "基盤モデル(VLA等)"}, {"key": "autonomy", "label": "自律度"},
        {"key": "strength", "label": "主な強み"},
    ],
}
EVENT_REQUIRED = (
    "event_id", "entity_id", "date", "category", "event_type",
    "headline", "summary", "score", "importance", "source", "source_tier",
)


class SchemaError(ValueError):
    """スキーマ違反。収集パイプラインはこれを捕捉して当該行をスキップ＋ログ。"""


def _require(d: dict, keys, ctx: str) -> None:
    missing = [k for k in keys if k not in d or d[k] in (None, "")]
    if missing:
        raise SchemaError(f"{ctx}: 必須フィールド欠落 {missing}")


def _enum(d: dict, key: str, allowed: set, ctx: str) -> None:
    if d[key] not in allowed:
        raise SchemaError(f"{ctx}: 未知の {key}={d[key]!r}（許容: {sorted(allowed)}）")


def _validate_history(d: dict, ctx: str) -> None:
    """entity.history があれば形を検証する（任意項目。無ければ何もしない）。"""
    hist = d.get("history")
    if hist in (None, []):
        return
    if not isinstance(hist, list):
        raise SchemaError(f"{ctx}: history は配列（実値 {type(hist).__name__}）")
    for i, h in enumerate(hist):
        if not isinstance(h, dict):
            raise SchemaError(f"{ctx}.history[{i}]: dict ではない")
        _require(h, HISTORY_ITEM_REQUIRED, f"{ctx}.history[{i}]")
        if "now" in h and not isinstance(h["now"], bool):
            raise SchemaError(f"{ctx}.history[{i}]: now は bool（実値 {h['now']!r}）")
        if "url" in h and not (isinstance(h["url"], str) and h["url"].startswith("http")):
            raise SchemaError(f"{ctx}.history[{i}]: url は http(s) 文字列（実値 {h['url']!r}）")
    # 新しい順（先頭=最新）を強制。最新(now)が先頭でないと横で左/縦で上に最新が来ない。
    if any(h.get("now") for h in hist) and not hist[0].get("now"):
        raise SchemaError(f"{ctx}: history は新しい順で記述し最新(now=true)を先頭に置く")


def _validate_sub_history(d: dict, ctx: str) -> None:
    """entity.sub_history があれば、サブモデル単位の履歴行として形を固定する。"""
    groups = d.get("sub_history")
    if groups in (None, []):
        return
    if not isinstance(groups, list):
        raise SchemaError(f"{ctx}: sub_history は配列（実値 {type(groups).__name__}）")
    for i, group in enumerate(groups):
        gctx = f"{ctx}.sub_history[{i}]"
        if not isinstance(group, dict):
            raise SchemaError(f"{gctx}: dict ではない")
        _require(group, ("model", "items"), gctx)
        if not isinstance(group["items"], list) or not group["items"]:
            raise SchemaError(f"{gctx}.items は非空配列")
        for j, item in enumerate(group["items"]):
            ictx = f"{gctx}.items[{j}]"
            if not isinstance(item, dict):
                raise SchemaError(f"{ictx}: dict ではない")
            _require(item, HISTORY_ITEM_REQUIRED, ictx)
            if "now" in item and not isinstance(item["now"], bool):
                raise SchemaError(f"{ictx}: now は bool（実値 {item['now']!r}）")
            if "url" in item and not (isinstance(item["url"], str) and item["url"].startswith("http")):
                raise SchemaError(f"{ictx}: url は http(s) 文字列（実値 {item['url']!r}）")


def _validate_comparison(d: dict, ctx: str) -> None:
    """entity.comparison（競合比較マトリクス）があれば形を検証する（任意項目）。

    軸は entity ではなく所属レンズ(category)の LENS_AXES が単一ソース（方針B）。
    entity は cols だけを持ち、各 col は所属レンズの全 axis キーのセルを揃える。
    """
    cmp = d.get("comparison")
    if cmp in (None, {}):
        return
    if not isinstance(cmp, dict):
        raise SchemaError(f"{ctx}: comparison は dict")
    if "axes" in cmp:  # 軸はレンズ共通が単一ソース。entity 独自軸は持たせない（方針B）。
        raise SchemaError(f"{ctx}: comparison.axes は不可（軸はレンズ共通 LENS_AXES が単一ソース）")
    axes = LENS_AXES.get(d.get("category"))
    if not axes:
        raise SchemaError(f"{ctx}: レンズ {d.get('category')!r} の比較軸（LENS_AXES）が未定義")
    cols = cmp.get("cols")
    if not isinstance(cols, list) or not cols:
        raise SchemaError(f"{ctx}: comparison.cols は非空配列")
    keys = [ax["key"] for ax in axes]
    for j, col in enumerate(cols):
        if not isinstance(col, dict):
            raise SchemaError(f"{ctx}.comparison.cols[{j}]: dict ではない")
        _require(col, ("name", "cells"), f"{ctx}.comparison.cols[{j}]")
        if not isinstance(col["cells"], dict):
            raise SchemaError(f"{ctx}.comparison.cols[{j}].cells は dict")
        missing = [k for k in keys if k not in col["cells"]]
        if missing:  # 穴あき表（描画の空セル）を作らせない
            raise SchemaError(
                f"{ctx}.comparison.cols[{j}]({col.get('name')}): 軸セル欠落 {missing}")


def _validate_future(d: dict, ctx: str) -> None:
    """modules.future（将来シナリオ）があれば形を検証する（任意項目）。"""
    fut = (d.get("modules") or {}).get("future")
    if fut in (None, []):
        return
    if not isinstance(fut, list):
        raise SchemaError(f"{ctx}: modules.future は配列")
    for i, f in enumerate(fut):
        if not isinstance(f, dict):
            raise SchemaError(f"{ctx}.modules.future[{i}]: dict ではない")
        _require(f, ("label", "title"), f"{ctx}.modules.future[{i}]")
        if "url" in f and not (isinstance(f["url"], str) and f["url"].startswith("http")):
            raise SchemaError(
                f"{ctx}.modules.future[{i}]: url は http(s) 文字列（実値 {f['url']!r}）")


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _validate_logo(d: dict, ctx: str) -> None:
    """entity.logo があるなら、PPT と SSG が読める形に固定する。"""
    if "logo" not in d:
        return
    logo = d["logo"]
    lctx = f"{ctx}.logo"
    if not isinstance(logo, dict):
        raise SchemaError(f"{lctx}: logo は object")
    status = logo.get("status")
    if status not in LOGO_STATUSES:
        raise SchemaError(f"{lctx}.status は {sorted(LOGO_STATUSES)} のいずれか")
    path = logo.get("path")
    if status == "missing":
        if path:
            raise SchemaError(f"{lctx}.path: missing では path を持たない")
    elif not (
        isinstance(path, str)
        and path.startswith(LOGO_PATH_PREFIX)
        and path.endswith(".png")
    ):
        raise SchemaError(
            f"{lctx}.path は {LOGO_PATH_PREFIX}<entity_id>.png 形式（実値 {path!r}）")
    if isinstance(path, str) and (
        "\\" in path or ".." in Path(path).parts or Path(path).is_absolute()
    ):
        raise SchemaError(f"{lctx}.path は repo 相対の安全な POSIX path（実値 {path!r}）")
    for key in ("source_url", "source_page"):
        url = logo.get(key)
        if url is not None and not (isinstance(url, str) and _is_http_url(url)):
            raise SchemaError(f"{lctx}.{key} は http(s) 文字列（実値 {url!r}）")
    fetched_at = logo.get("fetched_at")
    if fetched_at is not None and not (isinstance(fetched_at, str) and _DATE_RE.match(fetched_at)):
        raise SchemaError(f"{lctx}.fetched_at は YYYY-MM-DD 文字列（実値 {fetched_at!r}）")
    note = logo.get("license_note")
    if note is not None and not (isinstance(note, str) and note.strip()):
        raise SchemaError(f"{lctx}.license_note は非空文字列")


def validate_entity(d: dict) -> dict:
    """L1 カルテ 1 件を検証して返す。不正なら SchemaError。"""
    ctx = f"entity[{d.get('entity_id')}]"
    _require(d, ENTITY_REQUIRED, ctx)
    _enum(d, "category", CATEGORIES, ctx)
    _enum(d, "kind", KINDS, ctx)
    _enum(d, "offering", OFFERINGS, ctx)
    _validate_history(d, ctx)
    _validate_sub_history(d, ctx)
    _validate_comparison(d, ctx)
    _validate_future(d, ctx)
    _validate_logo(d, ctx)
    if "overview" in d and not (isinstance(d["overview"], str) and d["overview"]):
        raise SchemaError(f"{ctx}: overview は非空文字列")
    # search_query は collect_rss.build_query が最優先で参照する RSS 検索クエリの override。
    # 一般英単語・著名異義語企業を持つ entity (例: Runway / Composer / Cosmos / Codex / Llama /
    # Figure / Devin) で「name + vendor」自動派生が AI 文脈ゼロの記事を引いてしまう class of
    # bugs を、entity 側に明示クエリを書けるようにすることで構造的に封じる
    # ([[feedback_check_design_principles]] §1: illegal state / §2: 境界 1 箇所集約)。
    # 任意フィールド: 未存在は OK (自動派生に fallback)、存在するなら非空文字列必須。
    if "search_query" in d and not (isinstance(d["search_query"], str) and d["search_query"].strip()):
        raise SchemaError(f"{ctx}: search_query は非空文字列（実値 {d['search_query']!r}）")
    return d


def _validate_event_extras(d: dict, ctx: str, known_entity_ids: set | None = None) -> None:
    """L2 デルタの任意拡張（出典URL・カルテ更新フラグ・要点・判断根拠・関連カルテ）の形を固定する。

    いずれも収集ジョブ(LLM)が埋める任意項目。無ければ SSG 側が従来表示にフォールバックする。
    - source_url: 記事の出典URL。フィードの飛び先に使う（http 必須）。
    - karte_updated: このデルタでカルテ(L1)が更新されたか。true なら UPDATE バッジを出す。
    - summary_points: フィードの箇条書き要約（3〜5件・非空文字列）。
    - rationale: 重要/影響/話題の3指標を「なぜそう判断したか」の根拠（3キー必須）。
    - related_entities: 主 entity_id 以外の関連カルテ ID 配列（任意・後方互換の補助フィールド・案 B）。
        1 件のニュースが複数 entity に紐づくときに並べる用。known_entity_ids が渡されたら参照整合まで見る。
    """
    su = d.get("source_url")
    if "source_url" in d:
        if not (isinstance(su, str) and su):
            raise SchemaError(f"{ctx}: source_url は非空文字列（実値 {su!r}）")
        parsed = urlparse(su)
        if parsed.scheme not in ("http", "https"):
            raise SchemaError(f"{ctx}: source_url の scheme は http(s) 必須（実値 {su!r}）")
        if not parsed.netloc:
            raise SchemaError(f"{ctx}: source_url に hostname がない（実値 {su!r}）")
        bad = [c for c in su if c in _URL_FORBIDDEN_CHARS]
        if bad:
            raise SchemaError(f"{ctx}: source_url に危険文字 {bad!r}（実値 {su!r}）")
    if "karte_updated" in d and not isinstance(d["karte_updated"], bool):
        raise SchemaError(f"{ctx}: karte_updated は bool（実値 {d['karte_updated']!r}）")
    pts = d.get("summary_points")
    if pts not in (None, []):
        if not isinstance(pts, list) or not all(isinstance(p, str) and p for p in pts):
            raise SchemaError(f"{ctx}: summary_points は非空文字列の配列")
        if not (3 <= len(pts) <= 5):
            raise SchemaError(f"{ctx}: summary_points は3〜5件（実件数 {len(pts)}）")
    rat = d.get("rationale")
    if rat not in (None, {}):
        if not isinstance(rat, dict):
            raise SchemaError(f"{ctx}: rationale は dict")
        missing = [k for k in ("importance", "impact", "buzz")
                   if not (isinstance(rat.get(k), str) and rat.get(k))]
        if missing:
            raise SchemaError(f"{ctx}: rationale に重要/影響/話題の根拠欠落 {missing}")
        # ラベル反復 ("high"/"mid"/"low" や「高と判定」等の短文) を物理的に弾く。
        # prompt は 40〜80 字を要求しているが、安全側で 20 字以上を最低条件とする
        # ([[feedback_check_design_principles]] §1: illegal state を表現できなくする)。
        too_short = [
            (k, len(rat[k]))
            for k in ("importance", "impact", "buzz")
            if len(rat[k]) < _RATIONALE_MIN_LEN
        ]
        if too_short:
            raise SchemaError(
                f"{ctx}: rationale の根拠が文章として短すぎる "
                f"(各 {_RATIONALE_MIN_LEN} 字以上必須 / 実値 {too_short})"
            )
    rel = d.get("related_entities")
    if rel not in (None, []):
        if not isinstance(rel, list) or not all(isinstance(r, str) and r for r in rel):
            raise SchemaError(f"{ctx}: related_entities は非空文字列の配列")
        if len(rel) > 5:
            raise SchemaError(f"{ctx}: related_entities は最大 5 件（実件数 {len(rel)}）")
        if d.get("entity_id") in rel:
            raise SchemaError(f"{ctx}: related_entities に主 entity_id={d['entity_id']!r} を含めない（重複表示の防止）")
        if len(set(rel)) != len(rel):
            raise SchemaError(f"{ctx}: related_entities に重複あり {rel!r}")
        if known_entity_ids is not None:
            missing_refs = [r for r in rel if r not in known_entity_ids]
            if missing_refs:
                raise SchemaError(f"{ctx}: related_entities の参照先 {missing_refs!r} が L1 に存在しない")


def gemini_response_schema() -> dict:
    """Gemini API の response_schema (JSON mode) に渡す dict を返す。

    _validate_event_extras と整合する形状（summary 20-280 / summary_points 3-5 件 / rationale 3 軸）
    を Gemini 側にも強制し、Python 側のリトライ回数を減らす。enum は EVENT_TYPES / IMPORTANCE と一致。
    schema 違反の単一ソースを本モジュールに集約する目的で、llm_gemini.py はここから import する。
    summary は 2026-06-04 にプロンプト指示 80-120 字 → 160-240 字へ倍量化したのに合わせて上限を引き上げた。
    """
    return {
        "type": "object",
        "required": ["is_relevant", "summary", "summary_points", "rationale", "score", "importance", "event_type"],
        "properties": {
            # 関連性ゲート (2026-06-07): 同名異義 (Runway=空港の滑走路/ファッションの Rent the Runway 等) や
            # entity が主題でない記事を抽出段階で is_relevant=false にし、collect_rss が event 化前に skip する。
            # 2026-06-06 の search_query 絞り込み (入力側) では Google News の緩いマッチを抑えきれなかったため、
            # 出力側ゲートを追加して二段で封じる ([[feedback_check_design_principles]] §1 illegal state +
            # §2 境界 1 箇所集約: 抽出スキーマが local/Gemini 共通の単一ソース)。
            "is_relevant": {"type": "boolean"},
            "relevance_reason": {"type": "string"},
            "summary": {"type": "string", "minLength": 20, "maxLength": 280},
            "summary_points": {
                "type": "array",
                "minItems": 3,
                "maxItems": 5,
                "items": {"type": "string", "minLength": 5},
            },
            "rationale": {
                "type": "object",
                "required": ["importance", "impact", "buzz"],
                "properties": {
                    "importance": {"type": "string", "minLength": _RATIONALE_MIN_LEN},
                    "impact": {"type": "string", "minLength": _RATIONALE_MIN_LEN},
                    "buzz": {"type": "string", "minLength": _RATIONALE_MIN_LEN},
                },
            },
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "importance": {"type": "string", "enum": sorted(IMPORTANCE)},
            "event_type": {"type": "string", "enum": sorted(EVENT_TYPES)},
        },
    }


def validate_event(d: dict, known_entity_ids: set) -> dict:
    """L2 デルタ 1 件を検証して返す。参照整合まで含めて確認する。"""
    ctx = f"event[{d.get('event_id')}]"
    _require(d, EVENT_REQUIRED, ctx)
    _enum(d, "category", CATEGORIES, ctx)
    _enum(d, "event_type", EVENT_TYPES, ctx)
    _enum(d, "source_tier", SOURCE_TIERS, ctx)
    _enum(d, "importance", IMPORTANCE, ctx)
    if not isinstance(d["score"], int) or not (0 <= d["score"] <= 100):
        raise SchemaError(f"{ctx}: score は 0-100 の int（実値 {d['score']!r}）")
    if d["entity_id"] not in known_entity_ids:
        raise SchemaError(f"{ctx}: 参照先 entity_id={d['entity_id']!r} が L1 に存在しない")
    _validate_event_extras(d, ctx, known_entity_ids)
    return d


def load_jsonl(path) -> list[dict]:
    """JSON Lines を読む。空行は無視。壊れた行は行番号付きで SchemaError。"""
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict] = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise SchemaError(f"{p.name}:{i} JSON パース失敗: {e}") from e
    return rows


def validate_store(entities_path, events_path) -> tuple[list[dict], list[dict]]:
    """両 jsonl をロードし、L1 → L2 の参照整合まで一括検証する単一ゲート。"""
    entities = [validate_entity(d) for d in load_jsonl(entities_path)]
    ids = {e["entity_id"] for e in entities}
    events = [validate_event(d, ids) for d in load_jsonl(events_path)]
    return entities, events
