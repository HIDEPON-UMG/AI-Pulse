from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import editorial_lint  # noqa: E402


def test_editorial_lint_replaces_us_senate_hearing_and_softens_exaggeration() -> None:
    extras = {
        "summary": "参議院の中国向けチップ販売に関する聴聞会招致で画期的な発言があった。",
        "summary_points": ["上院聴聞会で業界標準となる可能性が高い動きが出た。"],
        "rationale": {
            "importance": "革命的な変化である。",
            "impact": "圧倒的な影響がある。",
            "buzz": "企業が公開したレビューとして話題である。",
        },
    }

    fixed, findings = editorial_lint.apply_editorial_lint(extras)

    assert fixed["summary"] == "米上院の中国向けチップ販売に関する公聴会への証言要請で注目される発言があった。"
    assert fixed["summary_points"] == ["米上院公聴会で標準化に影響する可能性がある動きが出た。"]
    assert fixed["rationale"]["importance"] == "大きな変化につながる変化である。"
    assert fixed["rationale"]["impact"] == "大きな影響がある。"
    assert extras["summary"] == "参議院の中国向けチップ販売に関する聴聞会招致で画期的な発言があった。"
    assert any(f["kind"] == "phrase_replacement" for f in findings)
    assert any(f["kind"] == "regex_replacement" for f in findings)
    assert any(f["kind"] == "soften_replacement" for f in findings)
    assert any(f["kind"] == "warn" for f in findings)
