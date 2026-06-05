"""apply_headline_ja.py の契約テスト ([[feedback_check_design_principles]] §4)。

class of bugs:
  - 翻訳対象判定が壊れて headline_ja を上書き or 日本語混在を再翻訳してしまう
  - --dry-run が実は LLM を呼んで課金が発生する
  - 途中で LLMError が出たら止まる (= 部分実行で events.jsonl が破損)

locked-in する不変条件:
  1. _scan_targets は headline_ja 既在 / 日本語混在 を必ず除外する
  2. --dry-run は llm_hybrid.translate_headline_ja を 1 度も呼ばない
  3. 途中で LLMError が起きても、成功した entry の headline_ja は最終 jsonl に残る
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import apply_headline_ja  # noqa: E402
import llm_hybrid  # noqa: E402


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(ev, ensure_ascii=False) for ev in events) + "\n",
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


class TestScanTargets:
    """_scan_targets は「翻訳対象だけ」を抽出する境界関数として正しく振る舞う。"""

    def test_excludes_existing_headline_ja_and_japanese_mixed(self) -> None:
        events = [
            {"event_id": "a", "headline": "Introducing Claude Opus 4.8"},  # 翻訳対象
            {
                "event_id": "b",
                "headline": "Already Translated",
                "headline_ja": "翻訳済みの見出し",
            },  # 既存 → 除外
            {"event_id": "c", "headline": "Qwen 技術リード辞任の舞台裏"},  # 日本語混在 → 除外
            {"event_id": "d", "headline": "Martin Scorsese Supports AI"},  # 翻訳対象
        ]
        targets = apply_headline_ja._scan_targets(events)
        assert [t[1]["event_id"] for t in targets] == ["a", "d"]


class TestDryRunDoesNotCallLLM:
    """--dry-run は LLM を 1 度も呼ばない (Gemini 課金が誤発生しない保証)。"""

    def test_dry_run_does_not_invoke_translate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        ev_path = tmp_path / "events.jsonl"
        _write_jsonl(ev_path, [{"event_id": "a", "headline": "Introducing Claude Opus 4.8"}])

        call_count = {"n": 0}

        def _fake_translate(*args, **kwargs):
            call_count["n"] += 1
            raise AssertionError("--dry-run で translate_headline_ja が呼ばれた (契約違反)")

        monkeypatch.setattr(llm_hybrid, "translate_headline_ja", _fake_translate)

        rc = apply_headline_ja.main(["--dry-run", "--data", str(ev_path)])
        assert rc == 0
        assert call_count["n"] == 0
        # jsonl は書き換えられていない (headline_ja が付与されていない)
        ev_after = _read_jsonl(ev_path)
        assert "headline_ja" not in ev_after[0]


class TestLLMErrorIsSkippedNotFatal:
    """途中で LLMError が出ても止まらず、成功 entry は events.jsonl に書き込まれる。"""

    def test_partial_failure_persists_successful_results(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ev_path = tmp_path / "events.jsonl"
        _write_jsonl(
            ev_path,
            [
                {"event_id": "a", "headline": "Introducing Claude Opus 4.8"},
                {"event_id": "b", "headline": "This One Will Fail"},
                {"event_id": "c", "headline": "Martin Scorsese Supports AI"},
            ],
        )

        def _fake_translate(headline: str, **kwargs) -> str:
            if "Fail" in headline:
                raise llm_hybrid.LLMError("意図的な失敗")
            return f"和訳: {headline}"

        monkeypatch.setattr(llm_hybrid, "translate_headline_ja", _fake_translate)

        rc = apply_headline_ja.main(["--data", str(ev_path)])
        assert rc == 0

        ev_after = {ev["event_id"]: ev for ev in _read_jsonl(ev_path)}
        # 成功した a / c は headline_ja が付き、失敗した b は触られていない
        assert ev_after["a"]["headline_ja"] == "和訳: Introducing Claude Opus 4.8"
        assert ev_after["c"]["headline_ja"] == "和訳: Martin Scorsese Supports AI"
        assert "headline_ja" not in ev_after["b"]


class TestEntityContextIsAlwaysNone:
    """translate_headline_ja は entity_context=None で呼ばれる ([[feedback_check_design_principles]] §4)。

    class of bugs (2026-06-05 観測): entity_id を entity_name として渡すと LLM が entity_id
    スラグ (例: 'flux' / 'physical-intelligence') を「公式な固有名詞表記」と誤解して
    翻訳結果に挿入・改変する事故が起きる。例:
      - 元 headline に無い "AI 企業 flux" の挿入
      - "Physical Intelligence" を entity_id 形式の "Physical-Intelligence" にハイフン連結化

    本テストは「未来の改修で entity_context を渡してしまう」逆行を防ぐ。
    """

    def test_translate_is_called_with_none_entity_context(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ev_path = tmp_path / "events.jsonl"
        _write_jsonl(
            ev_path,
            [
                {
                    "event_id": "a",
                    "entity_id": "flux",
                    "category": "media",
                    "headline": "Introducing Claude Opus 4.8",
                },
            ],
        )

        captured: dict = {}

        def _fake_translate(headline: str, *, entity_context=None, **kwargs) -> str:
            captured["entity_context"] = entity_context
            return "和訳"

        monkeypatch.setattr(llm_hybrid, "translate_headline_ja", _fake_translate)

        rc = apply_headline_ja.main(["--data", str(ev_path)])
        assert rc == 0
        # events.jsonl に entity_id="flux" があっても entity_context として渡されない
        assert captured["entity_context"] is None
