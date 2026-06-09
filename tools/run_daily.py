"""日次バッチ: L2 RSS 収集 + 当日追加エンティティのカルテ fast 更新 + サイト再生成

Task Scheduler から scripts/run_daily.ps1 経由で毎日 7:00 に実行。
claude -p / SDK 不使用。NotebookLM CLI（fast モード）を直接呼び出す。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import backfill_thumb  # noqa: E402
import collect_rss  # noqa: E402
import generate_pages  # noqa: E402
import quality_audit  # noqa: E402
import research_notebooklm as nb  # noqa: E402
import schema  # noqa: E402

DATA = ROOT / "data"
AUTH_REFRESH_ATTEMPTS = 3
AUTH_RETRY_SECONDS = 20


def _fast_update(entity: dict, *, auth_checked: bool = False) -> None:
    """1 エンティティを fast モードで NotebookLM 収集 → carte_fields → apply_deepdive。"""
    eid = entity["entity_id"]
    query = collect_rss.build_query(entity)
    print(f"  カルテ更新 [{eid}] query={query!r}")
    if not auth_checked:
        nb.ensure_auth()
    # ノートブック作成（fast: 通常 1〜3 分）
    cp = nb._nb(["create", f"AI-Pulse daily {eid}"])
    nb_id = nb._parse_notebook_id(cp.stdout)
    nb._nb([
        "source", "add-research", query,
        "--mode", "fast", "--import-all", "--timeout", "300",
        "-n", nb_id,
    ])
    # axis ごと ask → carte_fields → 永続化
    fields = nb.build_carte_fields(entity, nb_id)
    nb.apply_deepdive(eid, fields)
    print(f"    完了: {eid}")


def run_daily() -> None:
    print("=== AI-Pulse 日次バッチ 開始 ===")
    update_failures: list[str] = []

    # Step 1: RSS 収集（L2 events）
    print("\n--- Step 1: RSS 収集 ---")
    result = collect_rss.collect_entities()
    added_events = result["added"]
    audit_records = result.get("quality_audit_records") or []

    # Step 2: 採用 event の軽量品質監査（観測レイヤーなので失敗しても本線は止めない）
    print("\n--- Step 2: 品質監査 ---")
    try:
        audit_stats = quality_audit.audit_records(audit_records)
        print(
            "品質監査完了: "
            f"監査 {audit_stats['audited']} 件 / ok {audit_stats['ok']} / "
            f"warn {audit_stats['warn']} / fail {audit_stats['fail']} / "
            f"error {audit_stats['errors']} / 辞書候補 {audit_stats['term_candidates']}"
        )
    except Exception as exc:
        print(f"品質監査失敗（本線継続）: {exc}", file=sys.stderr)

    # Step 3: 当日更新エンティティのカルテ fast 更新
    if not added_events:
        print("新着なし。カルテ更新をスキップします。")
    else:
        updated_eids = list({ev["entity_id"] for ev in added_events})
        print(f"\n--- Step 3: カルテ fast 更新 ({len(updated_eids)} 件) ---")
        try:
            nb.ensure_auth(
                allow_login=False,
                refresh_attempts=AUTH_REFRESH_ATTEMPTS,
                retry_seconds=AUTH_RETRY_SECONDS,
            )
        except Exception as exc:
            print(
                f"  NotebookLM 認証 preflight 失敗。カルテ fast 更新をスキップします: {exc}",
                file=sys.stderr,
            )
            update_failures.extend(updated_eids)
        else:
            entities, _ = schema.validate_store(DATA / "entities.jsonl", DATA / "events.jsonl")
            by_id = {e["entity_id"]: e for e in entities}
            for eid in updated_eids:
                entity = by_id.get(eid)
                if entity is None:
                    continue
                try:
                    _fast_update(entity, auth_checked=True)
                except Exception as exc:
                    print(
                        f"    カルテ更新失敗 ({eid})。NotebookLM 認証 refresh 後に 1 回だけ再試行します: {exc}",
                        file=sys.stderr,
                    )
                    try:
                        nb.ensure_auth(
                            allow_login=False,
                            refresh_attempts=AUTH_REFRESH_ATTEMPTS,
                            retry_seconds=AUTH_RETRY_SECONDS,
                        )
                        _fast_update(entity, auth_checked=True)
                    except Exception as retry_exc:
                        print(f"    カルテ更新失敗 ({eid}): {retry_exc}", file=sys.stderr)
                        update_failures.append(eid)
                time.sleep(3)

    # Step 4: サムネイル補完
    print("\n--- Step 4: サムネイル補完 ---")
    backfill_thumb.backfill()

    # Step 5: サイト再生成
    print("\n--- Step 5: サイト再生成 ---")
    generate_pages.main()
    if update_failures:
        print(
            f"カルテ更新失敗: {len(update_failures)} 件 ({', '.join(update_failures)})。"
            "日次本線は完了（RSS収集・品質監査・サイト再生成済み）。",
            file=sys.stderr,
        )
    print("=== 日次バッチ 完了 ===")


if __name__ == "__main__":
    run_daily()
