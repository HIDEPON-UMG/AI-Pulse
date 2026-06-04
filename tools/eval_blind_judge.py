"""flash-lite(Gemini) vs qwen3:14b vs 35B-A3B 抽出品質の盲検ジャッジ採点（N 拡大版）。

使い方:
    python tools/eval_blind_judge.py            # 既定 N=12
    python tools/eval_blind_judge.py 15         # サンプル数指定

「ローカルに置換して Gemini との品質差分が許容範囲か」を最終判断するための定量評価。

評価条件（= 計画アーキテクチャを反映して公平化。本番コードは触らず本スクリプト内 monkeypatch で適用）:
- **強調契約を無効化**: 「強調記法はコード付与へ移す」決定済みのため、LLM には強調を課さない条件で実質品質を測る。
- **maxLength を 400 に緩和**: 語中切れ(maxLength:280 のハード切断)confound を全モデルから除去。
- **3 contestant 同条件**: flash-lite / qwen3:14b / 35B-A3B に同じプロンプト・同じ(緩和)スキーマ・temp 0.4。

盲検ジャッジ:
- 各サンプルで 3 出力を候補 A/B/C に index ローテーションで shuffle（モデル名隠蔽 + 位置バイアス回避）。
- gemini-2.5-flash が本文を見て rubric 採点（factual / summary_quality / points_quality / rationale_quality 各 1-5）。
- A/B/C をモデルへ復元し、観点別平均と flash-lite 比デルタを集計。
- 注意: ジャッジが Gemini 系のため flash-lite 有利の系統誤差リスクあり。rubric を客観軸に寄せて緩和し、集計は人(Claude)が中立確認する。

本番 events.jsonl は触らない。出力:
- docs/eval/2026-06-04_blind_judge.md（レポート）
- docs/eval/2026-06-04_blind_judge_raw.json（再現用の生スコア）
"""
from __future__ import annotations

import copy
import json
import sys
import time
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import config  # noqa: E402
import fetch_article  # noqa: E402
import schema  # noqa: E402
import llm_gemini  # noqa: E402
import llm_local  # noqa: E402
from eval_flash_vs_lite import build_meta_from_event  # noqa: E402
from google.genai import types  # noqa: E402

DATA = ROOT / "data"
REPORT = ROOT / "docs" / "eval" / "2026-06-04_blind_judge.md"
RAW = ROOT / "docs" / "eval" / "2026-06-04_blind_judge_raw.json"

JUDGE_MODEL = "gemini-2.5-flash"
SUMMARY_MAXLEN_RELAXED = 400
JUDGE_BODY_CHARS = 2000

# (表示名, バックエンド, モデルタグ)
CONTESTANTS = [
    ("flash-lite", "gemini", "gemini-2.5-flash-lite"),
    ("qwen3:14b", "local", "qwen3:14b"),
    ("35B-A3B", "local", "hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-IQ3_XXS"),
]
DIMS = ["factual", "summary_quality", "points_quality", "rationale_quality"]


# === 評価条件の monkeypatch（本スクリプト内に閉じる） ===
def _install_eval_conditions() -> None:
    # 1) maxLength 緩和スキーマ（毎回コピーを返す）
    base = llm_gemini.schema.gemini_response_schema()
    base["properties"]["summary"]["maxLength"] = SUMMARY_MAXLEN_RELAXED
    schema.gemini_response_schema = lambda: copy.deepcopy(base)
    # 2) 強調契約を外す（強調以外の検証は原実装をそのまま使い、EmphasisShortageError だけ握り潰す）
    orig_check = llm_gemini._check_shape
    def _check_no_emphasis(payload):
        try:
            orig_check(payload)
        except llm_gemini.EmphasisShortageError:
            pass  # この eval では強調はコード付与前提なので無効化
    llm_gemini._check_shape = _check_no_emphasis


def pick_samples(events: list[dict], n: int) -> list[dict]:
    """(category,event_type) 初出を優先して多様性確保 → 不足分は均等間隔で補充。"""
    seen: set = set()
    first: list[dict] = []
    rest: list[dict] = []
    for ev in events:
        combo = (ev["category"], ev["event_type"])
        if combo not in seen:
            seen.add(combo)
            first.append(ev)
        else:
            rest.append(ev)
    selected = first[:n]
    if len(selected) < n and rest:
        need = n - len(selected)
        step = max(1, len(rest) // need)
        for i in range(0, len(rest), step):
            selected.append(rest[i])
            if len(selected) >= n:
                break
    return selected[:n]


def gen_gemini(text: str, meta: dict, model: str):
    original = config.GEMINI_MODEL
    try:
        config.GEMINI_MODEL = model
        return llm_gemini.generate_event_extras(text, meta)
    except llm_gemini.LLMError as exc:
        return f"LLMError: {exc}"
    finally:
        config.GEMINI_MODEL = original


def gen_local(text: str, meta: dict, tag: str):
    original = config.OLLAMA_MODEL
    t0 = time.time()
    try:
        config.OLLAMA_MODEL = tag
        return llm_local.generate_event_extras(text, meta), time.time() - t0
    except llm_gemini.LLMError as exc:
        return f"LLMError: {exc}", time.time() - t0
    finally:
        config.OLLAMA_MODEL = original


def _judge_schema() -> dict:
    cand = {
        "type": "object",
        "required": [*DIMS, "comment"],
        "properties": {
            **{d: {"type": "integer", "minimum": 1, "maximum": 5} for d in DIMS},
            "comment": {"type": "string"},
        },
    }
    return {
        "type": "object",
        "required": ["A", "B", "C"],
        "properties": {"A": cand, "B": cand, "C": cand},
    }


def judge_sample(body: str, cand_map: dict[str, dict]) -> dict | str:
    """候補 A/B/C を本文照合で採点。戻り値は {A:{...},B:{...},C:{...}} または err 文字列。"""
    blocks = []
    for letter in ("A", "B", "C"):
        out = cand_map[letter]
        shown = {
            "summary": out.get("summary", ""),
            "summary_points": out.get("summary_points", []),
            "rationale": out.get("rationale", {}),
            "score": out.get("score"),
            "importance": out.get("importance"),
            "event_type": out.get("event_type"),
        }
        blocks.append(f"【候補{letter}】\n{json.dumps(shown, ensure_ascii=False, indent=1)}")
    prompt = (
        "あなたは AI ニュース抽出の品質評価者です。下の【記事本文】に対して生成された 3 つの抽出候補 "
        "(A/B/C) を採点してください。3 候補は同一記事から作られた JSON 抽出です。\n"
        "**重要: 強調記法(**太字** / ==marker== / __下線__)やマークアップの有無・スタイルは一切評価しない。"
        "内容の実質だけを見ること。**\n\n"
        "採点軸（各 1-5、5 が最良）:\n"
        "- factual: 本文に対する事実正確性。本文に無い数値・固有名詞・因果の捏造や歪曲があれば減点。\n"
        "- summary_quality: summary の情報量・要点把握・完結性。途中で文が切れていたら減点。\n"
        "- points_quality: summary_points の網羅性と具体性（固有名詞・数値・対比の有無）。\n"
        "- rationale_quality: importance/impact/buzz の論理的深さ。"
        "単に値ラベル(high/mid 等)を反復しているだけなら減点、含意・波及・矛盾の指摘まで踏み込んでいれば加点。\n\n"
        f"【記事本文】(先頭 {JUDGE_BODY_CHARS} 字)\n{body[:JUDGE_BODY_CHARS]}\n\n"
        + "\n\n".join(blocks)
        + "\n\n3 候補すべてを JSON で採点してください。"
    )
    try:
        client = llm_gemini._get_client()
        resp = client.models.generate_content(
            model=JUDGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=_judge_schema(),
                temperature=0.2,
            ),
        )
        raw = (resp.text or "").strip()
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001 - ジャッジ失敗は当該サンプルだけ捨てる
        return f"JudgeError: {type(exc).__name__}: {exc}"


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    _install_eval_conditions()

    events: list[dict] = []
    with (DATA / "events.jsonl").open(encoding="utf-8") as f:
        for line in f:
            ev = json.loads(line)
            if "-gem" in ev["event_id"]:
                events.append(ev)
    selected = pick_samples(events, n)
    print(f"-gem events: {len(events)} / selected: {len(selected)}（N={n} 指定）")

    # --- フェーズ A: 本文取得 + flash-lite ---
    samples: list[dict] = []
    for i, ev in enumerate(selected, 1):
        print(f"\n--- [A {i}/{len(selected)}] {ev['event_id']} ---")
        try:
            text = fetch_article.extract(ev["source_url"])["text"]
        except fetch_article.ArticleFetchError as exc:
            print(f"  本文取得失敗: {exc} → 除外")
            continue
        meta = build_meta_from_event(ev)
        print(f"  本文 {len(text)} 字 → flash-lite")
        out = gen_gemini(text, meta, "gemini-2.5-flash-lite")
        time.sleep(2.0)
        samples.append({"ev": ev, "text": text, "meta": meta, "out": {"flash-lite": out}})

    # --- フェーズ B: ローカル各モデル（ロード 1 回ずつ） ---
    lat: dict[str, list[float]] = {}
    for disp, backend, tag in CONTESTANTS:
        if backend != "local":
            continue
        lat[disp] = []
        print(f"\n=== ローカル {disp} ===")
        for i, s in enumerate(samples, 1):
            o, dt = gen_local(s["text"], s["meta"], tag)
            s["out"][disp] = o
            if not isinstance(o, str):
                lat[disp].append(dt)
            print(f"  [{i}/{len(samples)}] {'OK' if not isinstance(o, str) else 'ERR'} {dt:.1f}s")

    # --- 完走率 ---
    names = [d for d, _, _ in CONTESTANTS]
    completion = {nm: sum(1 for s in samples if not isinstance(s["out"].get(nm), str)) for nm in names}

    # --- フェーズ C: 盲検ジャッジ（3 モデルすべて成功したサンプルのみ採点） ---
    print("\n=== 盲検ジャッジ採点 ===")
    judged = 0
    agg: dict[str, dict[str, list[int]]] = {nm: {d: [] for d in DIMS} for nm in names}
    per_sample_judge: list[dict] = []
    for i, s in enumerate(samples):
        outs = s["out"]
        if any(isinstance(outs.get(nm), str) for nm in names):
            continue  # 3 モデル揃っていないサンプルは採点対象外
        # index ローテーションで A/B/C を割当（位置バイアス回避・決定論的 shuffle）
        rot = i % len(names)
        order = [names[(rot + k) % len(names)] for k in range(len(names))]
        letters = ["A", "B", "C"]
        cand_map = {letters[k]: outs[order[k]] for k in range(len(names))}
        letter_to_model = {letters[k]: order[k] for k in range(len(names))}
        res = judge_sample(s["text"], cand_map)
        time.sleep(2.0)
        if isinstance(res, str):
            print(f"  [{s['ev']['event_id']}] {res}")
            continue
        judged += 1
        rec = {"event_id": s["ev"]["event_id"], "scores": {}}
        for letter, model in letter_to_model.items():
            sc = res.get(letter, {})
            rec["scores"][model] = sc
            for d in DIMS:
                if isinstance(sc.get(d), int):
                    agg[model][d].append(sc[d])
        per_sample_judge.append(rec)
        line = " / ".join(
            f"{m}:{sum(res[L].get(d,0) for d in DIMS)/4:.2f}"
            for L, m in letter_to_model.items()
        )
        print(f"  [{s['ev']['event_id']}] {line}")

    # --- 集計 ---
    def avg(xs: list[int]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    model_dim_avg = {nm: {d: avg(agg[nm][d]) for d in DIMS} for nm in names}
    model_overall = {nm: avg([model_dim_avg[nm][d] for d in DIMS]) for nm in names}
    base = "flash-lite"

    print("\n=== 集計（flash-lite 基準デルタ）===")
    for nm in names:
        delta = model_overall[nm] - model_overall[base]
        print(f"  {nm:12s} 総合 {model_overall[nm]:.2f}  Δ{delta:+.2f}  完走 {completion[nm]}/{len(samples)}")

    # --- レポート ---
    lines = [
        f"# 盲検ジャッジ採点: flash-lite vs qwen3:14b vs 35B-A3B（{date.today().isoformat()}）\n",
        "## 方法\n",
        f"- N={len(samples)}（本文取得成功サンプル。-gem イベントから category×event_type 多様性優先で選定）",
        f"- 採点対象 {judged} 件（3 モデルすべて成功したサンプルのみ）",
        "- 評価条件: **強調契約を無効化**（強調=コード付与前提）+ **maxLength を 400 に緩和**（語中切れ除去）。3 モデル同条件。",
        f"- ジャッジ: `{JUDGE_MODEL}` が本文を見て盲検採点（候補 A/B/C は index ローテーションで shuffle・モデル名隠蔽・マークアップは評価対象外）。",
        "- **バイアス注記**: ジャッジが Gemini 系のため flash-lite 有利の系統誤差リスクあり。rubric を客観軸（事実=本文照合 / 完全性=切れ / rationale=ラベル反復減点）に寄せて緩和。\n",
        "## 完走率（強調無効・maxLength緩和の条件下）\n",
        "| モデル | 完走 |",
        "|---|---|",
    ]
    for nm in names:
        lines.append(f"| {nm} | {completion[nm]}/{len(samples)} |")
    lines.append("")
    lines.append("## 盲検スコア集計（各軸 1-5・5 が最良 / Δ は flash-lite 基準）\n")
    lines.append("| モデル | factual | summary | points | rationale | 総合 | Δ総合 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for nm in names:
        m = model_dim_avg[nm]
        delta = model_overall[nm] - model_overall[base]
        lines.append(
            f"| {nm} | {m['factual']:.2f} | {m['summary_quality']:.2f} | {m['points_quality']:.2f} | "
            f"{m['rationale_quality']:.2f} | **{model_overall[nm]:.2f}** | {delta:+.2f} |"
        )
    lines.append("")
    lines.append("## スループット\n")
    for disp in lat:
        xs = lat[disp]
        if xs:
            a = sum(xs) / len(xs)
            lines.append(f"- **{disp}**: 平均 {a:.1f}s/件 ／ 76 件直列推定 約 {a*76/60:.0f} 分")
    lines.append("")
    lines.append("## サンプル別スコア（総合平均）\n")
    lines.append("| event_id | " + " | ".join(names) + " |")
    lines.append("|---|" + "|".join(["---:"] * len(names)) + "|")
    for rec in per_sample_judge:
        cells = []
        for nm in names:
            sc = rec["scores"].get(nm, {})
            ov = sum(sc.get(d, 0) for d in DIMS) / 4 if sc else 0
            cells.append(f"{ov:.2f}")
        lines.append(f"| {rec['event_id']} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## 評価所感（手動追記欄）\n- 品質差分は許容範囲か: \n- 最終モデル選定: \n")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    RAW.write_text(json.dumps({
        "n": len(samples), "judged": judged, "completion": completion,
        "model_dim_avg": model_dim_avg, "model_overall": model_overall,
        "per_sample": per_sample_judge, "latency": lat,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nレポート: {REPORT}\n生スコア: {RAW}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
