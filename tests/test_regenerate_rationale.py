"""regenerate_rationale.py の契約テスト ([[feedback_check_design_principles]] §4)。

class of bugs:
  - 「rationale 文章 (20+ 字) は既に持っている」event を誤って再生成して上書きしてしまう
  - --dry-run が実は LLM を呼んで課金が発生する
  - 途中で LLMError が出たら止まる (= 部分実行で events.jsonl が破損)
  - entity_context を渡してしまい entity_id スラグ混入事故 (Part 6 と同じクラス)

locked-in する不変条件:
  1. _scan_targets は「文章 rationale 既在 (各値 20+ 字)」を必ず除外する
  2. --dry-run は llm_hybrid.regenerate_rationale を 1 度も呼ばない
  3. 途中で LLMError が起きても、成功した entry の rationale は最終 jsonl に残る
  4. regenerate_rationale は entity_context=None で呼ばれる
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import llm_hybrid  # noqa: E402
import regenerate_rationale  # noqa: E402


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(ev, ensure_ascii=False) for ev in events) + "\n",
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _full_rationale(prefix: str = "ok") -> dict:
    """20 字以上の文章 rationale を生成 (テスト fixture 用)。"""
    return {
        "importance": f"{prefix} 重要度を高と判定する根拠の文章サンプル (20 字以上の要件を満たす)",
        "impact": f"{prefix} 影響度を高と判定する根拠の文章サンプル (20 字以上の要件を満たす)",
        "buzz": f"{prefix} 話題性を高と判定する根拠の文章サンプル (20 字以上の要件を満たす)",
    }


class TestScanTargets:
    """_scan_targets は「再生成対象だけ」を抽出する境界関数として正しく振る舞う。"""

    def test_excludes_full_rationale_and_includes_short_or_missing(self) -> None:
        events = [
            {"event_id": "a", "rationale": {"importance": "high", "impact": "high", "buzz": "high"}},  # 4字
            {"event_id": "b", "rationale": _full_rationale("b")},  # 文章 → 除外
            {"event_id": "c"},  # rationale 無し → 対象
            {"event_id": "d", "rationale": {"importance": "高と判定", "impact": "mid", "buzz": "high"}},  # 全部短い
            {"event_id": "e", "rationale": "not-a-dict"},  # 型違反 → 対象
        ]
        targets = regenerate_rationale._scan_targets(events)
        assert [t[1]["event_id"] for t in targets] == ["a", "c", "d", "e"]


class TestDryRunDoesNotCallLLM:
    """--dry-run は LLM を 1 度も呼ばない (Gemini 課金事故ガード)。"""

    def test_dry_run_does_not_invoke_regenerate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ev_path = tmp_path / "events.jsonl"
        _write_jsonl(ev_path, [
            {"event_id": "a", "rationale": {"importance": "high", "impact": "high", "buzz": "high"},
             "headline": "h", "summary": "s", "summary_points": ["p1"], "importance": "high"},
        ])

        def _fake_regen(*args, **kwargs):
            raise AssertionError("--dry-run で regenerate_rationale が呼ばれた (契約違反)")

        monkeypatch.setattr(llm_hybrid, "regenerate_rationale", _fake_regen)

        rc = regenerate_rationale.main(["--dry-run", "--data", str(ev_path)])
        assert rc == 0
        ev_after = _read_jsonl(ev_path)
        # rationale は書き換えられていない (元の "high" のまま)
        assert ev_after[0]["rationale"]["importance"] == "high"


class TestLLMErrorIsSkippedNotFatal:
    """途中で LLMError が出ても止まらず、成功 entry は events.jsonl に書き込まれる。"""

    def test_partial_failure_persists_successful_results(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ev_path = tmp_path / "events.jsonl"
        _write_jsonl(ev_path, [
            {"event_id": "a", "rationale": {"importance": "high", "impact": "high", "buzz": "high"},
             "headline": "ha", "summary": "sa", "summary_points": ["p"], "importance": "high"},
            {"event_id": "b", "rationale": {"importance": "high", "impact": "high", "buzz": "high"},
             "headline": "hb-fail", "summary": "sb", "summary_points": ["p"], "importance": "high"},
            {"event_id": "c", "rationale": {"importance": "high", "impact": "high", "buzz": "high"},
             "headline": "hc", "summary": "sc", "summary_points": ["p"], "importance": "high"},
        ])

        def _fake_regen(headline, *args, **kwargs):
            if "fail" in headline:
                raise llm_hybrid.LLMError("意図的な失敗")
            return _full_rationale(headline)

        monkeypatch.setattr(llm_hybrid, "regenerate_rationale", _fake_regen)

        rc = regenerate_rationale.main(["--data", str(ev_path)])
        assert rc == 0

        ev_after = {ev["event_id"]: ev for ev in _read_jsonl(ev_path)}
        # 成功した a / c は新 rationale が付き、失敗した b は元の "high" のまま残る
        assert ev_after["a"]["rationale"]["importance"].startswith("ha ")
        assert ev_after["c"]["rationale"]["importance"].startswith("hc ")
        assert ev_after["b"]["rationale"]["importance"] == "high"


class TestEntityContextIsAlwaysNone:
    """regenerate_rationale は entity_context=None で呼ばれる (Part 6 同様 / [[feedback_check_design_principles]] §4)。

    class of bugs: entity_id を entity_name として渡すと LLM が entity_id スラグを「公式名」と
    誤解して rationale 文章に挿入する (Part 6 で観測した flux 捏造と同種のリスク)。
    """

    def test_regenerate_is_called_with_none_entity_context(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ev_path = tmp_path / "events.jsonl"
        _write_jsonl(ev_path, [
            {"event_id": "a", "entity_id": "flux", "category": "media",
             "rationale": {"importance": "high", "impact": "high", "buzz": "high"},
             "headline": "h", "summary": "s", "summary_points": ["p"], "importance": "high"},
        ])

        captured: dict = {}

        def _fake_regen(headline, summary, summary_points, importance_label, *, entity_context=None, **kwargs):
            captured["entity_context"] = entity_context
            return _full_rationale()

        monkeypatch.setattr(llm_hybrid, "regenerate_rationale", _fake_regen)

        rc = regenerate_rationale.main(["--data", str(ev_path)])
        assert rc == 0
        # events.jsonl に entity_id="flux" があっても entity_context として渡されない
        assert captured["entity_context"] is None
