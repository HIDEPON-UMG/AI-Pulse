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
from pathlib import Path

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


def validate_entity(d: dict) -> dict:
    """L1 カルテ 1 件を検証して返す。不正なら SchemaError。"""
    ctx = f"entity[{d.get('entity_id')}]"
    _require(d, ENTITY_REQUIRED, ctx)
    _enum(d, "category", CATEGORIES, ctx)
    _enum(d, "kind", KINDS, ctx)
    _enum(d, "offering", OFFERINGS, ctx)
    _validate_history(d, ctx)
    _validate_comparison(d, ctx)
    _validate_future(d, ctx)
    return d


def _validate_event_extras(d: dict, ctx: str) -> None:
    """L2 デルタの任意拡張（出典URL・カルテ更新フラグ・要点・判断根拠）の形を固定する。

    いずれも収集ジョブ(LLM)が埋める任意項目。無ければ SSG 側が従来表示にフォールバックする。
    - source_url: 記事の出典URL。フィードの飛び先に使う（http 必須）。
    - karte_updated: このデルタでカルテ(L1)が更新されたか。true なら UPDATE バッジを出す。
    - summary_points: フィードの箇条書き要約（3〜5件・非空文字列）。
    - rationale: 重要/影響/話題の3指標を「なぜそう判断したか」の根拠（3キー必須）。
    """
    su = d.get("source_url")
    if "source_url" in d and not (isinstance(su, str) and su.startswith("http")):
        raise SchemaError(f"{ctx}: source_url は http(s) 文字列（実値 {su!r}）")
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
    _validate_event_extras(d, ctx)
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
