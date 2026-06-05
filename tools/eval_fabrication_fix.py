"""捏造対策（実験 B）の factual 改善幅を盲検ジャッジで実測する。

使い方:
    python tools/eval_fabrication_fix.py            # 既定 N=12

35B-A3B の factual 忠実度（固有名詞・数値の捏造）を、以下の対策で改善できるか測る:
  (1) 本文打切りの緩和（MAX_BODY_CHARS 3000→8000）
  (2) temperature を下げる（0.4→0.1）
  (3) grounding 強化プロンプト（prompts/extract_grounded.md・強調規則を削除し事実忠実性を絶対規則化）

3 アームを同条件（強調無効・maxLength 400）で生成し、本文照合に強い factual 重視の盲検ジャッジで採点:
  - flash-lite-現状 : 本文3000 / temp0.4 / 現行プロンプト（factual 基準線）
  - 35B-現状(BASE)  : 本文3000 / temp0.4 / 現行プロンプト
  - 35B-対策(TREAT) : 本文8000 / temp0.1 / grounding プロンプト

出力: docs/eval/2026-06-04_fabrication_fix.md / _raw.json。本番 events.jsonl は触らない。
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
from eval_blind_judge import pick_samples, _install_eval_conditions, _judge_schema, DIMS  # noqa: E402
from google.genai import types  # noqa: E402

REPORT = ROOT / "docs" / "eval" / "2026-06-04_fabrication_fix.md"
RAW = ROOT / "docs" / "eval" / "2026-06-04_fabrication_fix_raw.json"

JUDGE_MODEL = "gemini-2.5-flash"
JUDGE_BODY_CHARS = 8000       # ジャッジは本文全量を見て factual を照合する
FETCH_MAX = 8000              # 8000 字版を取得（BASE は [:3000] にスライス）

OLLAMA_35B = "hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-IQ3_XXS"
# 旧本線プロンプト。2026-06-05 追補11 で本線 PROMPT_PATH を extract_grounded.md に切替したため、
# ここでは過去 eval 再走のために .archive/ 経由で参照する（本線回帰には使わない）。
BASE_PROMPT = ROOT / "prompts" / ".archive" / "gemini_summarize.md"
GROUNDED_PROMPT = ROOT / "prompts" / "extract_grounded.md"

# (表示名, backend, モデル, 本文文字数, temp, プロンプト)
ARMS = [
    ("flash-lite-現状", "gemini", "gemini-2.5-flash-lite", 3000, 0.4, "base"),
    ("35B-現状",        "local",  OLLAMA_35B,              3000, 0.4, "base"),
    ("35B-対策",        "local",  OLLAMA_35B,              8000, 0.1, "grounded"),
]
NAMES = [a[0] for a in ARMS]


def run_arm(arm, body: str, meta: dict):
    """1 アーム生成。戻り値: (payload|err文字列, latency|None)。"""
    name, backend, model, _chars, temp, prompt_kind = arm
    llm_gemini.PROMPT_PATH = GROUNDED_PROMPT if prompt_kind == "grounded" else BASE_PROMPT
    if backend == "gemini":
        orig = config.GEMINI_MODEL
        try:
            config.GEMINI_MODEL = model
            return llm_gemini.generate_event_extras(body, meta), None
        except llm_gemini.LLMError as exc:
            return f"LLMError: {exc}", None
        finally:
            config.GEMINI_MODEL = orig
    else:
        om, ot = config.OLLAMA_MODEL, config.OLLAMA_TEMPERATURE
        t0 = time.time()
        try:
            config.OLLAMA_MODEL = model
            config.OLLAMA_TEMPERATURE = temp
            return llm_local.generate_event_extras(body, meta), time.time() - t0
        except llm_gemini.LLMError as exc:
            return f"LLMError: {exc}", time.time() - t0
        finally:
            config.OLLAMA_MODEL, config.OLLAMA_TEMPERATURE = om, ot


def judge_sample(body: str, cand_map: dict) -> dict | str:
    """factual を本文照合で厳密採点する盲検ジャッジ。"""
    blocks = []
    for letter in ("A", "B", "C"):
        out = cand_map[letter]
        shown = {
            "summary": out.get("summary", ""),
            "summary_points": out.get("summary_points", []),
            "rationale": out.get("rationale", {}),
        }
        blocks.append(f"【候補{letter}】\n{json.dumps(shown, ensure_ascii=False, indent=1)}")
    prompt = (
        "あなたは AI ニュース抽出の品質評価者です。下の【記事本文】に対する 3 つの抽出候補 (A/B/C) を採点してください。\n"
        "**最重要: factual を本文照合で厳密に判定する。** 候補が本文に存在しない固有名詞・人名・組織名・地名・"
        "数値・金額・日付を含めていたら（＝捏造）factual を大きく減点する。本文にある事実だけで構成されていれば高評価。"
        "ただし本文の一部を書かない（省略）ことは factual の減点対象にしない。\n"
        "**強調記法やマークアップの有無・スタイルは一切評価しない。**\n\n"
        "採点軸（各 1-5、5 が最良）:\n"
        "- factual: 本文に対する事実正確性（捏造があれば大減点）\n"
        "- summary_quality: 要点把握・完結性\n"
        "- points_quality: 網羅性と具体性（ただし本文にある範囲で）\n"
        "- rationale_quality: importance/impact/buzz の論理的深さ（値ラベルの反復だけなら減点）\n\n"
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
        return json.loads((resp.text or "").strip())
    except Exception as exc:  # noqa: BLE001
        return f"JudgeError: {type(exc).__name__}: {exc}"


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    _install_eval_conditions()           # 強調無効 + maxLength 400（3 アーム同条件）
    config.MAX_BODY_CHARS = FETCH_MAX     # 8000 字まで取得（BASE は後でスライス）

    events = []
    with (ROOT / "data" / "events.jsonl").open(encoding="utf-8") as f:
        for line in f:
            ev = json.loads(line)
            if "-gem" in ev["event_id"]:
                events.append(ev)
    selected = pick_samples(events, n)
    print(f"-gem events: {len(events)} / selected: {len(selected)}（N={n}）")

    samples = []
    lat = {nm: [] for nm in NAMES}
    for i, ev in enumerate(selected, 1):
        print(f"\n--- [{i}/{len(selected)}] {ev['event_id']} ---")
        try:
            full = fetch_article.extract(ev["source_url"])["text"]
        except fetch_article.ArticleFetchError as exc:
            print(f"  本文取得失敗: {exc} → 除外")
            continue
        meta = build_meta_from_event(ev)
        print(f"  本文 {len(full)} 字（8000上限）")
        outs = {}
        for arm in ARMS:
            name, backend, _m, chars, _t, _p = arm
            body = full[:chars]
            out, dt = run_arm(arm, body, meta)
            outs[name] = out
            if dt is not None and not isinstance(out, str):
                lat[name].append(dt)
            print(f"    {name:16s} {'OK' if not isinstance(out, str) else 'ERR'}"
                  f"{f' {dt:.1f}s' if dt else ''}")
        samples.append({"ev": ev, "full": full, "outs": outs})

    # 完走率
    completion = {nm: sum(1 for s in samples if not isinstance(s["outs"].get(nm), str)) for nm in NAMES}

    # 盲検ジャッジ（3 アーム全成功サンプルのみ）
    print("\n=== 盲検ジャッジ ===")
    agg = {nm: {d: [] for d in DIMS} for nm in NAMES}
    per_sample = []
    judged = 0
    for i, s in enumerate(samples):
        if any(isinstance(s["outs"].get(nm), str) for nm in NAMES):
            continue
        rot = i % len(NAMES)
        order = [NAMES[(rot + k) % len(NAMES)] for k in range(len(NAMES))]
        letters = ["A", "B", "C"]
        cand_map = {letters[k]: s["outs"][order[k]] for k in range(len(NAMES))}
        l2m = {letters[k]: order[k] for k in range(len(NAMES))}
        res = judge_sample(s["full"], cand_map)
        time.sleep(2.0)
        if isinstance(res, str):
            print(f"  [{s['ev']['event_id']}] {res}")
            continue
        judged += 1
        rec = {"event_id": s["ev"]["event_id"], "scores": {}}
        for letter, model in l2m.items():
            sc = res.get(letter, {})
            rec["scores"][model] = sc
            for d in DIMS:
                if isinstance(sc.get(d), int):
                    agg[model][d].append(sc[d])
        per_sample.append(rec)
        fac = " / ".join(f"{m}:fact{res[L].get('factual','?')}" for L, m in l2m.items())
        print(f"  [{s['ev']['event_id']}] {fac}")

    def avg(xs):
        return sum(xs) / len(xs) if xs else 0.0
    dim_avg = {nm: {d: avg(agg[nm][d]) for d in DIMS} for nm in NAMES}
    overall = {nm: avg([dim_avg[nm][d] for d in DIMS]) for nm in NAMES}

    print("\n=== 集計 ===")
    for nm in NAMES:
        print(f"  {nm:16s} factual {dim_avg[nm]['factual']:.2f}  総合 {overall[nm]:.2f}  完走 {completion[nm]}/{len(samples)}")
    d_fac = dim_avg["35B-対策"]["factual"] - dim_avg["35B-現状"]["factual"]
    d_vs_fl = dim_avg["35B-対策"]["factual"] - dim_avg["flash-lite-現状"]["factual"]
    print(f"  factual 改善（対策−現状）: {d_fac:+.2f}")
    print(f"  factual 対 flash-lite     : {d_vs_fl:+.2f}")

    # レポート
    lines = [
        f"# 捏造対策（実験 B）factual 改善計測（{date.today().isoformat()}）\n",
        "## 目的\n",
        "35B-A3B の factual 忠実度を 3 対策（本文8000字 / temp0.1 / grounding 強化プロンプト）で改善できるか、"
        "盲検ジャッジで head-to-head に実測する。\n",
        "## 条件\n",
        f"- N={len(samples)} / 採点 {judged} 件（3 アーム全成功サンプル）",
        "- 共通: 強調無効 + maxLength 400。ジャッジ `gemini-2.5-flash` が本文全量を見て factual を厳密照合（捏造大減点・省略は減点せず）。",
        "- アーム: flash-lite-現状（本文3000/temp0.4/現行）/ 35B-現状（本文3000/temp0.4/現行）/ 35B-対策（本文8000/temp0.1/grounding）\n",
        "## 結果（各軸 1-5）\n",
        "| アーム | factual | summary | points | rationale | 総合 | 完走 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for nm in NAMES:
        m = dim_avg[nm]
        lines.append(
            f"| {nm} | {m['factual']:.2f} | {m['summary_quality']:.2f} | {m['points_quality']:.2f} | "
            f"{m['rationale_quality']:.2f} | {overall[nm]:.2f} | {completion[nm]}/{len(samples)} |"
        )
    lines.append("")
    lines.append(f"- **factual 改善（35B 対策 − 35B 現状）: {d_fac:+.2f}**")
    lines.append(f"- **factual 35B対策 − flash-lite現状: {d_vs_fl:+.2f}**（0 以上なら捏造面で Gemini に並んだ）\n")
    lines.append("## スループット\n")
    for nm in NAMES:
        if lat[nm]:
            a = sum(lat[nm]) / len(lat[nm])
            lines.append(f"- {nm}: 平均 {a:.1f}s/件 ／ 76件 約 {a*76/60:.0f} 分")
    lines.append("\n## サンプル別 factual\n| event_id | " + " | ".join(NAMES) + " |")
    lines.append("|---|" + "|".join(["---:"] * len(NAMES)) + "|")
    for rec in per_sample:
        cells = [str(rec["scores"].get(nm, {}).get("factual", "-")) for nm in NAMES]
        lines.append(f"| {rec['event_id']} | " + " | ".join(cells) + " |")
    lines.append("\n## 評価所感（手動追記欄）\n- factual は許容水準に達したか: \n- 採用プロンプト/パラメータ: \n")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    RAW.write_text(json.dumps({
        "n": len(samples), "judged": judged, "completion": completion,
        "dim_avg": dim_avg, "overall": overall,
        "delta_factual_treat_minus_base": d_fac, "delta_factual_vs_flashlite": d_vs_fl,
        "per_sample": per_sample, "latency": lat,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nレポート: {REPORT}\n生スコア: {RAW}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
