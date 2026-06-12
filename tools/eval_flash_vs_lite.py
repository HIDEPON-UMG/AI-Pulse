"""flash vs flash-lite 品質比較スクリプト（オフラインで完結 / events.jsonl は触らない）。

使い方:
    python tools/eval_flash_vs_lite.py

5 件の多様な -gem event を選び、publisher 本文を再取得し、
gemini-2.5-flash と gemini-2.5-flash-lite で同じ記事を処理させ、
docs/eval/2026-06-04_flash_vs_flash_lite.md に side-by-side 比較レポートを出力する。

なぜ独立スクリプトか:
- 本番 events.jsonl は flash 出力で確定済み（76 件）。これを汚さないため。
- config.GEMINI_MODEL を一時切替しつつ generate_event_extras を 2 回呼ぶ。
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

DATA = ROOT / "data"
REPORT = ROOT / "docs" / "eval" / "2026-06-04_flash_vs_flash_lite.md"


def pick_diverse(events: list[dict], n: int = 5) -> list[dict]:
    """category/event_type の組合せで多様性を確保した n 件。"""
    seen = set()
    selected: list[dict] = []
    for ev in events:
        combo = (ev["category"], ev["event_type"])
        if combo not in seen:
            seen.add(combo)
            selected.append(ev)
        if len(selected) >= n:
            break
    return selected


def build_meta_from_event(ev: dict) -> dict:
    """カルテ情報を最小限で組み立てる。"""
    return {
        "title": ev["headline"],
        "entity_name": ev.get("entity_id", "").replace("-", " ").title(),
        "category": ev.get("category", ""),
        "vendor": "",
        "entity_positioning": "",
    }


def call_with_model(article_text: str, meta: dict, model: str) -> dict | str:
    """config.GEMINI_MODEL を一時的に差し替えて generate_event_extras を呼ぶ。"""
    original = config.GEMINI_MODEL
    try:
        config.GEMINI_MODEL = model
        return llm_gemini.generate_event_extras(article_text, meta)
    except llm_gemini.LLMError as exc:
        return f"LLMError: {exc}"
    finally:
        config.GEMINI_MODEL = original


def fmt(payload, key: str) -> str:
    """payload の key を Markdown safe な文字列にする。"""
    if isinstance(payload, str):
        return f"`{payload[:120]}`"
    val = payload.get(key, "")
    if isinstance(val, list):
        return "\n".join(f"  - {item}" for item in val)
    if isinstance(val, dict):
        return "\n".join(f"  - **{k}**: {v}" for k, v in val.items())
    return str(val)


def main() -> int:
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    events: list[dict] = []
    with (DATA / "events.jsonl").open(encoding="utf-8") as f:
        for line in f:
            ev = json.loads(line)
            if "-gem" in ev["event_id"]:
                events.append(ev)
    print(f"-gem events: {len(events)}")

    selected = pick_diverse(events, n=5)
    print(f"selected diverse {len(selected)} events:")
    for ev in selected:
        print(f"  {ev['event_id']} | {ev['category']}/{ev['event_type']} | {ev['headline'][:60]}")

    lines: list[str] = [
        f"# flash vs flash-lite 品質比較（{date.today().isoformat()}）\n",
        "## 目的\n",
        (
            "`gemini-2.5-flash-lite` への切替を判断するため、本番 `gemini-2.5-flash` で生成した 76 件のうち、"
            "category × event_type の多様性で 5 件を選び、同じ publisher 本文を両モデルに処理させて出力を並べる。\n"
        ),
        "## サンプル選定\n",
        "| event_id | category | event_type | score (flash) | headline |",
        "|---|---|---|---:|---|",
    ]
    for ev in selected:
        lines.append(
            f"| {ev['event_id']} | {ev['category']} | {ev['event_type']} | "
            f"{ev['score']} | {ev['headline'][:70]} |"
        )
    lines.append("")

    for i, ev in enumerate(selected, 1):
        print(f"\n--- [{i}/{len(selected)}] {ev['event_id']} 処理中 ---")
        url = ev["source_url"]
        try:
            article = fetch_article.extract(url)
            text = article["text"]
        except fetch_article.ArticleFetchError as exc:
            print(f"  本文取得失敗: {exc} → スキップ")
            lines.append(f"\n### {i}. {ev['headline'][:70]}\n")
            lines.append(f"**本文再取得失敗**: `{exc}`\n")
            continue

        print(f"  本文 {len(text)} 文字 取得")
        meta = build_meta_from_event(ev)

        print("  → flash 呼び出し中...")
        out_flash = call_with_model(text, meta, "gemini-2.5-flash")
        time.sleep(2.0)
        print("  → flash-lite 呼び出し中...")
        out_lite = call_with_model(text, meta, "gemini-2.5-flash-lite")
        time.sleep(2.0)

        lines.append(f"\n### {i}. {ev['headline'][:80]}\n")
        lines.append(f"- **publisher**: {url}")
        lines.append(f"- **category / event_type (flash)**: {ev['category']} / {ev['event_type']}")
        lines.append(f"- **本文文字数（再取得時点）**: {len(text)}\n")

        lines.append("#### flash 出力\n")
        if isinstance(out_flash, str):
            lines.append(f"```\n{out_flash}\n```\n")
        else:
            lines.append(f"- **score / importance / event_type**: {out_flash.get('score')} / "
                         f"{out_flash.get('importance')} / {out_flash.get('event_type')}")
            lines.append(f"- **summary**: {out_flash.get('summary', '')}")
            lines.append("- **summary_points**:")
            lines.append(fmt(out_flash, "summary_points"))
            lines.append("- **rationale**:")
            lines.append(fmt(out_flash, "rationale"))
            lines.append("")

        lines.append("#### flash-lite 出力\n")
        if isinstance(out_lite, str):
            lines.append(f"```\n{out_lite}\n```\n")
        else:
            lines.append(f"- **score / importance / event_type**: {out_lite.get('score')} / "
                         f"{out_lite.get('importance')} / {out_lite.get('event_type')}")
            lines.append(f"- **summary**: {out_lite.get('summary', '')}")
            lines.append("- **summary_points**:")
            lines.append(fmt(out_lite, "summary_points"))
            lines.append("- **rationale**:")
            lines.append(fmt(out_lite, "rationale"))
            lines.append("")

    lines.append("\n## 評価所感（手動記入欄）\n")
    lines.append("- summary 品質: \n- summary_points 適切性: \n- rationale 論理性: \n- score 妥当性: \n- event_type 分類精度: \n")
    lines.append("\n## 推奨判断\n")
    lines.append("- [ ] flash-lite に切替（無料 + 品質許容）\n- [ ] flash 維持（品質差大きい）\n- [ ] ハイブリッド（特定 entity だけ flash）\n")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nレポート出力: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
