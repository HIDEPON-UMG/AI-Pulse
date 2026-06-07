"""ローカル (Ollama) 各モデル vs gemini flash / flash-lite の抽出品質 N-way 比較。

使い方:
    python tools/eval_local_extraction.py

抽出処理（generate_event_extras）をローカル LLM に置換できるか・どのローカルモデルが最良かを判断するため、
eval_flash_vs_lite と同じ 5 サンプル（category × event_type 多様）の publisher 本文を再取得し、
gemini-2.5-flash / gemini-2.5-flash-lite / LOCAL_MODELS（think=false・同一プロンプト・同一スキーマ拘束・temp 0.4）
で side-by-side 比較レポートを docs/eval/2026-06-04_qwen3_vs_gemini.md に出力する。

GPU 16GB に複数ローカルモデルは同時に乗らないため、**モデルごとにまとめて回す**（フェーズ B）。
これでローカルモデルのロードは各 1 回で済み、サンプルごとに qwen3↔27B を切替えるスラッシングを避ける。

なぜ独立スクリプトか:
- 本番 events.jsonl は触らない（flash 出力で確定済みの 76 件を汚さない）。
- 既存の flash-vs-lite レポートも上書きしない（別ファイルに出す）。
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

# Windows CP932 環境でも日本語・em dash を print できるよう stdout を utf-8 強制
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import config  # noqa: E402
import fetch_article  # noqa: E402
import llm_gemini  # noqa: E402
import llm_local  # noqa: E402
from eval_flash_vs_lite import build_meta_from_event, fmt, pick_diverse  # noqa: E402  # 選定/整形を再利用

DATA = ROOT / "data"
REPORT = ROOT / "docs" / "eval" / "2026-06-04_qwen3_vs_gemini.md"

# (表示名, Ollama タグ)。GPU に同時搭載できないのでフェーズ B で 1 モデルずつ通す。
LOCAL_MODELS = [
    ("qwen3:14b", "qwen3:14b"),
    ("Qwen3.6-27B (IQ3_XXS)", "hf.co/unsloth/Qwen3.6-27B-GGUF:UD-IQ3_XXS"),
]


def call_gemini(text: str, meta: dict, model: str):
    """config.GEMINI_MODEL を一時差替えして generate_event_extras を呼ぶ。"""
    original = config.GEMINI_MODEL
    try:
        config.GEMINI_MODEL = model
        return llm_gemini.generate_event_extras(text, meta)
    except llm_gemini.LLMError as exc:
        return f"LLMError: {exc}"
    finally:
        config.GEMINI_MODEL = original


def call_local(text: str, meta: dict, ollama_tag: str):
    """config.OLLAMA_MODEL を一時差替えしてローカル呼び出し。戻り値: (payload|err文字列, 秒)。"""
    original = config.OLLAMA_MODEL
    t0 = time.time()
    try:
        config.OLLAMA_MODEL = ollama_tag
        return llm_local.generate_event_extras(text, meta), time.time() - t0
    except llm_gemini.LLMError as exc:
        return f"LLMError: {exc}", time.time() - t0
    finally:
        config.OLLAMA_MODEL = original


def render_block(lines: list[str], title: str, out, latency: float | None = None) -> None:
    head = f"#### {title} 出力"
    if latency is not None and not isinstance(out, str):
        head += f"（{latency:.1f}s）"
    lines.append(head + "\n")
    if isinstance(out, str):
        lines.append(f"```\n{out}\n```\n")
        return
    lines.append(
        f"- **score / importance / event_type**: {out.get('score')} / "
        f"{out.get('importance')} / {out.get('event_type')}"
    )
    lines.append(f"- **summary**: {out.get('summary', '')}")
    lines.append("- **summary_points**:")
    lines.append(fmt(out, "summary_points"))
    lines.append("- **rationale**:")
    lines.append(fmt(out, "rationale"))
    lines.append("")


def main() -> int:
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    events: list[dict] = []
    with (DATA / "events.jsonl").open(encoding="utf-8") as f:
        for line in f:
            ev = json.loads(line)
            if "-gem" in ev["event_id"]:
                events.append(ev)
    selected = pick_diverse(events, n=5)
    print(f"-gem events: {len(events)} / selected diverse: {len(selected)}")

    # --- フェーズ A: 本文取得 + gemini flash / flash-lite（サンプル単位） ---
    samples: list[dict] = []
    for i, ev in enumerate(selected, 1):
        print(f"\n--- [A {i}/{len(selected)}] {ev['event_id']} 本文+gemini ---")
        url = ev["source_url"]
        try:
            article = fetch_article.extract(url)
            text = article["text"]
        except fetch_article.ArticleFetchError as exc:
            print(f"  本文取得失敗: {exc} → スキップ")
            samples.append({"ev": ev, "url": url, "fetch_error": str(exc)})
            continue
        print(f"  本文 {len(text)} 文字 取得")
        meta = build_meta_from_event(ev)
        print("  → flash")
        out_flash = call_gemini(text, meta, "gemini-2.5-flash")
        time.sleep(2.0)
        print("  → flash-lite")
        out_lite = call_gemini(text, meta, "gemini-2.5-flash-lite")
        time.sleep(2.0)
        samples.append({
            "ev": ev, "url": url, "text": text, "meta": meta,
            "out_flash": out_flash, "out_lite": out_lite, "local": {},
        })

    # --- フェーズ B: ローカルモデルごとにまとめて全サンプル（ロード 1 回ずつ） ---
    local_lat: dict[str, list[float]] = {disp: [] for disp, _ in LOCAL_MODELS}
    for disp, tag in LOCAL_MODELS:
        print(f"\n=== ローカルモデル {disp}（{tag}） ===")
        for i, s in enumerate(samples, 1):
            if "text" not in s:
                continue
            out, lat = call_local(s["text"], s["meta"], tag)
            s["local"][disp] = (out, lat)
            if not isinstance(out, str):
                local_lat[disp].append(lat)
            status = "OK" if not isinstance(out, str) else "ERR"
            print(f"  [{i}/{len(samples)}] {status} {lat:.1f}s")

    # --- レポート出力 ---
    lines: list[str] = [
        f"# ローカル各モデル vs gemini flash/flash-lite 抽出品質比較（{date.today().isoformat()}）\n",
        "## 目的\n",
        (
            "抽出処理（generate_event_extras）をローカル LLM に置換できるか・どのローカルモデルが最良かを判断するため、"
            "eval_flash_vs_lite と同じ 5 サンプルの publisher 本文を再取得し、"
            "gemini-2.5-flash / gemini-2.5-flash-lite / "
            + " / ".join(disp for disp, _ in LOCAL_MODELS)
            + "（think=false・同一プロンプト・同一スキーマ拘束・temp 0.4）で side-by-side 比較する。\n"
        ),
        "## サンプル選定\n",
        "| event_id | category | event_type | headline |",
        "|---|---|---|---|",
    ]
    for ev in selected:
        lines.append(
            f"| {ev['event_id']} | {ev['category']} | {ev['event_type']} | {ev['headline'][:60]} |"
        )
    lines.append("")

    for i, s in enumerate(samples, 1):
        ev = s["ev"]
        lines.append(f"\n### {i}. {ev['headline'][:80]}\n")
        if "text" not in s:
            lines.append(f"**本文再取得失敗**: `{s['fetch_error']}`\n")
            continue
        lines.append(f"- **publisher**: {s['url']}")
        lines.append(f"- **category / event_type (ground truth)**: {ev['category']} / {ev['event_type']}")
        lines.append(f"- **本文文字数（再取得時点）**: {len(s['text'])}\n")
        render_block(lines, "flash", s["out_flash"])
        render_block(lines, "flash-lite", s["out_lite"])
        for disp, _ in LOCAL_MODELS:
            out, lat = s["local"].get(disp, ("(未実行)", None))
            render_block(lines, disp, out, lat)

    lines.append("\n## ローカル実測スループット\n")
    for disp, _ in LOCAL_MODELS:
        lats = local_lat[disp]
        if lats:
            avg = sum(lats) / len(lats)
            lines.append(
                f"- **{disp}**: 1 件平均 **{avg:.1f}s**（{len(lats)} 件・初回はモデルロードで割高）／ "
                f"76 件直列推定 **約 {avg * 76 / 60:.0f} 分**（RPM/RPD 天井なし）"
            )
        else:
            lines.append(f"- **{disp}**: 有効サンプルなし（全件 LLMError）")
    lines.append("")

    lines.append("\n## 評価所感（手動追記欄）\n")
    lines.append(
        "- summary 完結性（maxLength 語中切れの有無）: \n"
        "- 事実精度 / 要点適切性: \n"
        "- rationale 論理性: \n"
        "- score / importance 妥当性: \n"
        "- event_type 分類精度: \n"
        "- 14b vs 27B どちらが抽出に優れるか: \n"
    )
    lines.append("\n## 推奨判断\n")
    lines.append(
        "- [ ] qwen3:14b に置換\n"
        "- [ ] Qwen3.6-27B に置換\n"
        "- [ ] flash-lite 維持\n"
        "- [ ] ハイブリッド（通常ローカル・失敗/GPU占有時に Gemini フォールバック）\n"
    )

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nレポート出力: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
