"""日次バッチ: L2 RSS 収集 + Ollama カルテ更新 + Repo Radar + サイト再生成

Task Scheduler から scripts/run_daily.ps1 経由で毎日 7:00 に実行。
claude -p / SDK / NotebookLM 不使用。Ollama で採用済み event からカルテを更新する。
"""
from __future__ import annotations

import sys
import time
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import backfill_thumb  # noqa: E402
import collect_buzz_posts  # noqa: E402
import collect_repo_radar  # noqa: E402
import collect_rss  # noqa: E402
import generate_pages  # noqa: E402
import quality_audit  # noqa: E402
import repo_radar_obsidian  # noqa: E402
import research_ollama as carte  # noqa: E402
import schema  # noqa: E402
from _proc.run import quiet_run  # noqa: E402

DATA = ROOT / "data"
PROJECT_FOLDERS = ROOT.parent
POWERSHELL_EXE = "powershell.exe"
TWITTER_RSS_RUNNER = PROJECT_FOLDERS / "twitter-rss" / "scripts" / "run_repo_radar_rss.ps1"
BUZZPOST_SEARCH_WORD_PATH = PROJECT_FOLDERS / "twitter-rss" / "data" / "buzzpost-searches.json"
BUZZPOST_SEARCH_UPDATE_SCRIPT = PROJECT_FOLDERS / "twitter-rss" / "scripts" / "update_buzzpost_searches.py"
IDEASTASH_VAULT = Path(os.environ.get("IDEASTASH_VAULT", Path.home() / "Obsidian" / "IdeaStash"))


def _fast_update(entity: dict, events: list[dict]) -> None:
    """1 エンティティを Ollama でカルテ更新する。"""
    eid = entity["entity_id"]
    query = collect_rss.build_query(entity)
    print(f"  カルテ更新 [{eid}] backend=ollama query={query!r}")
    carte.update_entity(entity, events)
    print(f"    完了: {eid}")


def _run_repo_radar_x_rss() -> None:
    """Repo Radar 用の X RSS を生成する。失敗しても日次本線は止めない。"""
    if not TWITTER_RSS_RUNNER.exists():
        print(f"WARN: Repo Radar X RSS runner が見つからないためスキップ: {TWITTER_RSS_RUNNER}")
        return
    cp = quiet_run(
        [
            POWERSHELL_EXE,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            TWITTER_RSS_RUNNER,
        ],
        timeout=600,
        check=False,
    )
    if cp.stdout:
        print(cp.stdout.rstrip())
    if cp.stderr:
        print(cp.stderr.rstrip(), file=sys.stderr)
    if cp.returncode != 0:
        print(f"WARN: Repo Radar X RSS 生成失敗 (exit {cp.returncode}) だが日次本線は続行する")
    else:
        print("Repo Radar X RSS 生成 完了")


def _run_buzzpost_x_rss() -> None:
    """BuzzPost 用の X RSS を生成する。失敗しても日次本線は止めない。"""
    if not TWITTER_RSS_RUNNER.exists():
        print(f"WARN: BuzzPost X RSS runner が見つからないためスキップ: {TWITTER_RSS_RUNNER}")
        return
    if BUZZPOST_SEARCH_UPDATE_SCRIPT.exists():
        update_cp = quiet_run(
            [sys.executable, BUZZPOST_SEARCH_UPDATE_SCRIPT],
            timeout=60,
            check=False,
        )
        if update_cp.stdout:
            print(update_cp.stdout.rstrip())
        if update_cp.stderr:
            print(update_cp.stderr.rstrip(), file=sys.stderr)
        if update_cp.returncode != 0:
            print(
                f"WARN: BuzzPost 検索語更新失敗 (exit {update_cp.returncode}) "
                "だが既存検索語で続行する"
            )
    if not BUZZPOST_SEARCH_WORD_PATH.exists():
        print(f"WARN: BuzzPost 検索語が見つからないためスキップ: {BUZZPOST_SEARCH_WORD_PATH}")
        return
    cp = quiet_run(
        [
            POWERSHELL_EXE,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            TWITTER_RSS_RUNNER,
            "-SearchWordPath",
            BUZZPOST_SEARCH_WORD_PATH,
            "-SkipSearchUpdate",
        ],
        timeout=600,
        check=False,
    )
    if cp.stdout:
        print(cp.stdout.rstrip())
    if cp.stderr:
        print(cp.stderr.rstrip(), file=sys.stderr)
    if cp.returncode != 0:
        print(f"WARN: BuzzPost X RSS 生成失敗 (exit {cp.returncode}) だが日次本線は続行する")
    else:
        print("BuzzPost X RSS 生成 完了")


def _export_repo_radar_obsidian() -> None:
    """Repo Radar 公開データを IdeaStash の Obsidian ノートへ同期する。"""
    vault = IDEASTASH_VAULT
    if not vault.exists():
        print(f"WARN: IdeaStash vault が見つからないため Repo Radar Obsidian 同期をスキップ: {vault}")
        return
    stats = repo_radar_obsidian.export_notes(
        collect_repo_radar.REPO_RADAR_PATH,
        vault / "repo-radar",
    )
    print(
        "Repo Radar Obsidian 同期: "
        f"written {stats['written']} / skipped {stats['skipped']}"
    )
    if stats["written"] <= 0:
        return
    if not (vault / ".git").exists():
        print("WARN: IdeaStash vault が git repo ではないため push をスキップ")
        return
    add = quiet_run(["git", "-C", str(vault), "add", "repo-radar"], timeout=60, check=False)
    if add.returncode != 0:
        print(f"WARN: IdeaStash repo-radar git add 失敗: {add.stderr}", file=sys.stderr)
        return
    diff = quiet_run(
        ["git", "-C", str(vault), "diff", "--cached", "--quiet", "--", "repo-radar"],
        timeout=60,
        check=False,
    )
    if diff.returncode == 0:
        return
    commit = quiet_run(
        ["git", "-C", str(vault), "commit", "-m", "sync: Repo Radar Obsidian notes [AI-Pulse]"],
        timeout=120,
        check=False,
    )
    if commit.returncode != 0:
        print(f"WARN: IdeaStash repo-radar commit 失敗: {commit.stderr}", file=sys.stderr)
        return
    push = quiet_run(["git", "-C", str(vault), "push"], timeout=180, check=False)
    if push.returncode != 0:
        print(f"WARN: IdeaStash repo-radar push 失敗: {push.stderr}", file=sys.stderr)
        return
    print("Repo Radar Obsidian GitHub 同期 完了")


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

    # Step 3: 当日更新エンティティのカルテ更新（Ollama）
    if not added_events:
        print("新着なし。カルテ更新をスキップします。")
    else:
        updated_eids = list({ev["entity_id"] for ev in added_events})
        print(f"\n--- Step 3: カルテ Ollama 更新 ({len(updated_eids)} 件) ---")
        entities, _ = schema.validate_store(DATA / "entities.jsonl", DATA / "events.jsonl")
        by_id = {e["entity_id"]: e for e in entities}
        by_event_eid: dict[str, list[dict]] = {}
        for ev in added_events:
            by_event_eid.setdefault(ev["entity_id"], []).append(ev)
        for eid in updated_eids:
            entity = by_id.get(eid)
            if entity is None:
                continue
            try:
                _fast_update(entity, by_event_eid.get(eid, []))
            except Exception as exc:
                print(f"    カルテ更新失敗 ({eid}): {exc}", file=sys.stderr)
                update_failures.append(eid)
            time.sleep(3)

    # Step 4: Repo Radar（カルテ更新後の観測レイヤー。失敗しても本線は止めない）
    print("\n--- Step 4: Repo Radar ---")
    _run_repo_radar_x_rss()
    try:
        radar_stats = collect_repo_radar.collect()
        print(
            "Repo Radar 完了: "
            f"candidates {radar_stats['candidates']} / "
            f"enriched {radar_stats['enriched']} / "
            f"evaluated {radar_stats['evaluated']} / "
            f"skipped {radar_stats['skipped']} / "
            f"degraded {radar_stats['degraded']} / "
            f"ollama_errors {radar_stats['ollama_errors']}"
        )
        _export_repo_radar_obsidian()
    except Exception as exc:
        print(f"Repo Radar 失敗（本線継続）: {exc}", file=sys.stderr)

    # Step 5: BuzzPost（生成AIコミュニティ観測レイヤー。失敗しても本線は止めない）
    print("\n--- Step 5: BuzzPost ---")
    _run_buzzpost_x_rss()
    try:
        buzz_stats = collect_buzz_posts.collect()
        print(
            "BuzzPost 完了: "
            f"collected {buzz_stats['collected']} / "
            f"written {buzz_stats['written']} / "
            f"degraded {buzz_stats['degraded']}"
        )
    except Exception as exc:
        print(f"BuzzPost 失敗（本線継続）: {exc}", file=sys.stderr)

    # Step 6: サムネイル補完
    print("\n--- Step 6: サムネイル補完 ---")
    backfill_thumb.backfill()

    # Step 7: サイト再生成
    print("\n--- Step 7: サイト再生成 ---")
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
