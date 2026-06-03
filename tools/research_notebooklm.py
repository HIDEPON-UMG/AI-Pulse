"""深掘りジョブ（長周期・非同期 2 段）: NotebookLM で対象カルテ（L1）を更新する。

段A kick_deep : notebooklm create/use → deep research を非同期キック → job-state 保存（待たない）。
段B collect   : job-state を読み、source list が ready なら ask --json で観点別回答を取得して返す。
              （30 分級のレイテンシを同期ブロックさせないため 2 段に割る。dataflow 図 ②）
カルテ各フィールドへの落とし込み（要約→positioning / competitors / C軸 / recommendation）は
LLM（claude -p, prompts/deepdive_notebooklm.md）が行い、その抽出結果を apply_deepdive で永続化する。

NotebookLM CLI（専用 venv に隔離。所在は memory reference_notebooklm_digest）:
  ~/.claude/tools/notebooklm-py/.venv/Scripts/notebooklm.exe（Path.home() 起点で解決）
全 subprocess 起動は _proc（CREATE_NO_WINDOW 強制）を通す。runner/spawner はテストで差し替え可能。
"""
from __future__ import annotations

import json
import sys
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
