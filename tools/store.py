"""書き込み境界: L2 デルタ / L1 カルテの掲載判定・重複排除・カルテ更新フック・永続化。

schema.py が「読込＋検証」の単一ゲートなのに対し、本モジュールは「生成＋書込」の単一ゲート。
収集系（research_websearch / research_notebooklm）はここだけを通してデータを更新し、
個別箇所で jsonl を直接 append したりカルテを直接書き換えたりしない（境界 1 箇所集約）。

不変条件（契約テスト tests/test_store.py で固定）:
- カルテ更新フックは参照先カルテが無ければ SchemaError（リンク切れを表現させない）。
- snapshot_date は後ろ向きに動かさない（古いニュースでカルテを巻き戻さない）。
- 同一 event_id / 同一内容のデルタは二重登録しない（同日重複の再発防止）。
"""
from __future__ import annotations

import json
from pathlib import Path

import config
import schema


def _content_key(ev: dict):
    """event_id とは別に内容で重複を見るためのキー（id 違いの同一ニュース対策）。"""
    return (ev["entity_id"], ev["event_type"], ev["date"], ev["headline"])


def dedupe_events(new_events, existing_events):
    """event_id と内容キーの両方で既存と重複する new を除く。返り値は (採用, 重複)。"""
    seen_ids = {e["event_id"] for e in existing_events}
    seen_keys = {_content_key(e) for e in existing_events}
    kept, dup = [], []
    for ev in new_events:
        if ev["event_id"] in seen_ids or _content_key(ev) in seen_keys:
            dup.append(ev)
        else:
            kept.append(ev)
            seen_ids.add(ev["event_id"])
            seen_keys.add(_content_key(ev))
    return kept, dup


def filter_by_score(events, score_min: int = config.SCORE_MIN):
    """掲載閾値未満を落とす。返り値は (採用, 不採用)。"""
    keep = [e for e in events if e.get("score", 0) >= score_min]
    drop = [e for e in events if e.get("score", 0) < score_min]
    return keep, drop


def apply_carte_hook(event: dict, entities_by_id: dict) -> dict:
    """L2 デルタ 1 件を L1 カルテへ反映するフック（dataflow 図の「カルテ更新フック」）。

    - 参照先カルテが無ければ SchemaError（リンク切れを表現させない）。
    - snapshot_date を後ろ向きに動かさず event.date まで進める（カルテが触れられた印）。
    - recent_events に event_id を backlink（重複排除・上限 cap、新しい順）。
    返り値は更新後の entity（in-place 更新した同一オブジェクト）。
    """
    eid = event["entity_id"]
    ent = entities_by_id.get(eid)
    if ent is None:
        raise schema.SchemaError(f"carte hook: 参照先 entity_id={eid!r} が L1 に存在しない")
    if event["date"] > ent.get("snapshot_date", ""):
        ent["snapshot_date"] = event["date"]
    recent = ent.setdefault("recent_events", [])
    if event["event_id"] not in recent:
        recent.insert(0, event["event_id"])
        del recent[config.RECENT_EVENTS_CAP:]
    return ent


def append_events(events_path, new_events) -> None:
    """検証済み new_events を jsonl に追記（utf-8 / ensure_ascii=False）。"""
    with Path(events_path).open("a", encoding="utf-8") as f:
        for ev in new_events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def write_entities(entities_path, entities) -> None:
    """カルテ全件を書き戻す（フック更新後の再永続化）。tmp→replace で原子的に。"""
    p = Path(entities_path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for e in entities:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    tmp.replace(p)


def ingest_events(entities_path, events_path, candidate_events) -> dict:
    """候補デルタを 検証→掲載閾値→重複排除→カルテ更新フック→永続化 する単一手順。

    速報・深掘りの両経路がこの 1 関数を共有する。
    返り値: {'added': [...], 'skipped_dup': int, 'skipped_score': int}
    """
    entities, existing = schema.validate_store(entities_path, events_path)
    by_id = {e["entity_id"]: e for e in entities}
    validated = [schema.validate_event(ev, set(by_id)) for ev in candidate_events]
    scored, low = filter_by_score(validated)
    kept, dup = dedupe_events(scored, existing)
    for ev in kept:
        apply_carte_hook(ev, by_id)
    if kept:
        append_events(events_path, kept)
        write_entities(entities_path, entities)
    return {"added": kept, "skipped_dup": len(dup), "skipped_score": len(low)}
