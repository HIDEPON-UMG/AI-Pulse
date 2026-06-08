"""深掘りジョブ（長周期・非同期 2 段）: NotebookLM で対象カルテ（L1）を更新する。

段A kick_deep : notebooklm create/use → deep research を非同期キック → job-state 保存（待たない）。
段B collect   : job-state を読み、source list が ready なら ask --json で観点別回答を取得して返す。
              （30 分級のレイテンシを同期ブロックさせないため 2 段に割る。dataflow 図 ②）
build_carte_fields: ソースが ready な notebook に対して axis ごとに ask し carte_fields を生成する。
              claude -p 不要。LENS_AXES の各軸を個別に質問し回答を直接 cells に入れる。
              apply_deepdive と組み合わせてカルテを更新する（run_daily / run_weekly が呼ぶ）。

NotebookLM CLI（専用 venv に隔離。所在は memory reference_notebooklm_digest）:
  ~/.claude/tools/notebooklm-py/.venv/Scripts/notebooklm.exe（Path.home() 起点で解決）
全 subprocess 起動は _proc（CREATE_NO_WINDOW 強制）を通す。runner/spawner はテストで差し替え可能。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import schema  # noqa: E402
import store  # noqa: E402
from _proc.run import quiet_run, spawn_detached  # noqa: E402

DATA = ROOT / "data"
JOBS = ROOT / "_meta" / "jobs"
NB_CLI = (
    Path.home() / ".claude" / "tools" / "notebooklm-py" / ".venv" / "Scripts" / "notebooklm.exe"
)


def _nb(args, *, runner=quiet_run, timeout=120):
    """notebooklm CLI を呼ぶ薄いラッパ。runner はテストで差し替え可能。"""
    return runner([str(NB_CLI), *args], timeout=timeout)


def ensure_auth(
    *,
    runner=quiet_run,
    allow_login: bool = True,
    refresh_attempts: int = 1,
    retry_seconds: float = 5.0,
) -> None:
    """NotebookLM 認証を温める。

    Task Scheduler などの非対話実行では login を完了できないため、日次バッチは
    allow_login=False で refresh の成否だけを見る。対話実行や週次の手動復旧では
    従来通り login で保存状態の更新を試せる。
    """
    last_exc: Exception | None = None
    for attempt in range(max(1, refresh_attempts)):
        try:
            _nb(["auth", "refresh"], runner=runner, timeout=30)
            return
        except Exception as exc:
            last_exc = exc
            if attempt < refresh_attempts - 1:
                print(
                    f"  NotebookLM auth refresh 失敗 ({attempt + 1}/{refresh_attempts})。"
                    f"{retry_seconds:g}秒後に再試行します: {exc}",
                    file=sys.stderr,
                )
                time.sleep(retry_seconds)
    if not allow_login:
        raise RuntimeError(
            f"NotebookLM auth refresh 失敗（非対話実行のため login は試行しません）: {last_exc}"
        ) from last_exc
    print(f"  NotebookLM auth refresh 失敗。login で再認証します: {last_exc}", file=sys.stderr)
    _nb(["login"], runner=runner, timeout=180)
    _nb(["auth", "refresh"], runner=runner, timeout=30)


def kick_deep(entity_id, theme, *, notebook_id=None,
              runner=quiet_run, spawner=spawn_detached) -> str:
    """段A: deep research を非同期キックし job-state を保存。notebook_id を返す。

    notebook_id を渡せば create 出力のパースを省く（orchestrator が create を実行して
    ID を読めるとき推奨。CLI 出力形式の推測に依存しない安全経路）。None のときだけ
    内部で create → _parse_notebook_id（ベストエフォート）する。
    """
    if notebook_id is None:
        cp = _nb(["create", theme], runner=runner)
        notebook_id = _parse_notebook_id(cp.stdout)
    _nb(["use", notebook_id], runner=runner)
    # deep は数分〜30 分。待たずにデタッチ起動し、段B で ready を拾う。
    spawner([
        str(NB_CLI), "-n", notebook_id, "source", "add-research", theme,
        "--mode", "deep", "--import-all", "--timeout", "3600",
    ])
    _save_job({
        "entity_id": entity_id, "theme": theme,
        "notebook_id": notebook_id, "status": "researching",
    })
    return notebook_id


def collect(entity_id, questions, *, runner=quiet_run) -> dict:
    """段B: source が ready なら ask --json で観点別回答を取得。未完なら status を返す。"""
    job = _load_job(entity_id)
    nid = job["notebook_id"]
    listing = _nb(["-n", nid, "source", "list", "--json"], runner=runner)
    sources = json.loads(listing.stdout or "[]")
    if not sources or not all(s.get("status") == "ready" for s in sources):
        return {"status": "researching", "ready": False, "sources": len(sources)}
    answers = []
    for q in questions:
        cp = _nb(["-n", nid, "ask", q, "--json", "--timeout", "120"], runner=runner)
        answers.append(json.loads(cp.stdout))
    job["status"] = "ready"
    _save_job(job)
    return {"status": "ready", "ready": True, "answers": answers}


def apply_deepdive(entity_id, carte_fields, entities_path=None, events_path=None) -> dict:
    """段B 後段: LLM が ask 回答から抽出したカルテ差分を L1 に反映して永続化。

    反映後も schema を満たすことを検証する（不正状態を持ち回らせない）。
    """
    entities_path = entities_path or DATA / "entities.jsonl"
    events_path = events_path or DATA / "events.jsonl"
    entities, _ = schema.validate_store(entities_path, events_path)
    by_id = {e["entity_id"]: e for e in entities}
    if entity_id not in by_id:
        raise schema.SchemaError(f"apply_deepdive: 未知の entity_id={entity_id!r}")
    by_id[entity_id].update(carte_fields)
    schema.validate_entity(by_id[entity_id])
    store.write_entities(entities_path, entities)
    return by_id[entity_id]


def build_carte_fields(entity: dict, nb_id: str, *, runner=quiet_run) -> dict:
    """NotebookLM の ask で overview + LENS_AXES 各軸に回答させ carte_fields を生成する。

    claude -p 不要。axis ごとに ask し回答を直接 cells に格納する（LLM 変換を省略）。
    返り値は apply_deepdive に渡せる dict（overview + comparison）。
    """
    eid = entity["entity_id"]
    name = entity.get("name", eid)
    category = entity.get("category", "")
    axes = schema.LENS_AXES.get(category, [])

    # overview（3〜5 文の説明）
    q_ov = (
        f"Summarize {name} in 3-5 sentences: what it is, who makes it, "
        f"its main use case, and its current position in the market. "
        f"Use only information from the registered sources. "
        f"If no information is available, write 'No information available.'"
    )
    ov_cp = _nb(["-n", nb_id, "ask", q_ov, "--timeout", "120"], runner=runner)
    overview = ov_cp.stdout.strip() or entity.get("overview", "")

    # LENS_AXES の各軸を axis ごとに ask → cells に直入れ
    cells: dict[str, str] = {}
    for axis in axes:
        key = axis["key"]
        label = axis["label"]
        q_axis = (
            f"About {name}: describe its '{label}' in 1-2 concise sentences. "
            f"Use only information from the registered sources. "
            f"If no information is available, write 'N/A'."
        )
        cp = _nb(["-n", nb_id, "ask", q_axis, "--timeout", "90"], runner=runner)
        cells[key] = cp.stdout.strip() or "N/A"
        time.sleep(1.0)  # ask 間の rate limit 対策

    fields: dict = {"overview": overview}
    if cells:
        # 既存 comparison の self 列を更新（他エンティティ列は保持）
        existing_cmp = entity.get("comparison") or {}
        existing_cols: list[dict] = list(existing_cmp.get("cols") or [])
        self_col = next((c for c in existing_cols if c.get("name") == name), None)
        if self_col is not None:
            self_col["cells"].update(cells)
        else:
            existing_cols.insert(0, {"name": name, "cells": cells})
        fields["comparison"] = {"cols": existing_cols}

    return fields


def _parse_notebook_id(stdout: str) -> str:
    """`notebooklm create` の出力から notebook_id をベストエフォートで拾う。

    実 CLI 出力形式は未確認（follow-up で現物確認）。誤検出を避けるため
    「英数 + - _ で 8 文字以上 かつ 数字を 1 つ以上含む」トークンに限定する
    （'notebook' のような英単語ラベルを弾く。NotebookLM の ID は UUID 様で数字を含む）。
    複数該当時は最長を採る。確実な経路は kick_deep(notebook_id=...) の明示指定。
    """
    candidates = []
    for tok in (stdout or "").replace("\n", " ").split():
        t = tok.strip().strip("'\"")
        if len(t) >= 8 and any(c.isdigit() for c in t) and all(c.isalnum() or c in "-_" for c in t):
            candidates.append(t)
    if not candidates:
        raise RuntimeError(
            f"notebook_id を解釈できない（kick_deep(notebook_id=...) で明示指定可）: {stdout!r}")
    return max(candidates, key=len)


def _job_path(entity_id) -> Path:
    return JOBS / f"{entity_id}.json"


def _save_job(job: dict) -> None:
    JOBS.mkdir(parents=True, exist_ok=True)
    _job_path(job["entity_id"]).write_text(
        json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _load_job(entity_id) -> dict:
    return json.loads(_job_path(entity_id).read_text(encoding="utf-8"))
