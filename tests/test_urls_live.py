#!/usr/bin/env python3
"""entities.jsonl / events.jsonl の URL 生存検証 契約テスト。

# なぜ重要か

LLM (Claude セッション) は記憶ベースで URL を捏造する既知バグがある (News-Grasp
2026-06-03 三菱UFJ FX_Monthly 事故で 803 件中 33 件 = 約 4% が 404/410)。AI-Pulse
でも entity.history[].url / entity.modules.future[].url / event.source_url が同じ
経路で捏造混入し得るので、契約テストとして locked-in する。

本テストは `tools/audit_urls.py --gate` を subprocess で呼び、直近 14 日に追加された
URL の 404/410 を防ぐ:
  1. push 前 audit (CLAUDE.md 記載) と同じ境界モジュールを CI/開発時にも適用 (二重ガード)
  2. 直近窓に限定することでテスト時間を ~30 秒以内に抑える
  3. 歴史的死リンク (リンク切れになった真正記事) は対象外 (別 ad-hoc 監査で扱う)

実行:
  ./.venv/Scripts/python.exe -m pytest tests/test_urls_live.py -v

ネットワーク不可環境では AI_PULSE_SKIP_URL_CHECK=1 で skip される。
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _network_available() -> bool:
    if os.environ.get("AI_PULSE_SKIP_URL_CHECK") == "1":
        return False
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=3.0):
            return True
    except OSError:
        return False


needs_network = pytest.mark.skipif(
    not _network_available(),
    reason="ネットワーク不可 (または AI_PULSE_SKIP_URL_CHECK=1)",
)


@pytest.mark.network
@needs_network
def test_recent_store_urls_are_alive():
    """直近 14 日の entity.history[].url / entity.modules.future[].url / event.source_url が
    すべて生存している契約。

    audit_urls.py --gate を CLI 経由で呼び exit 0 を確認する。push 前 audit と同じ境界
    モジュールを通すので、本テストが通れば push gate も通る (二重ガードのうち先発)。
    """
    cmd = [sys.executable, "-m", "tools.audit_urls", "--gate"]
    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    assert result.returncode == 0, (
        "直近 14 日の entities.jsonl / events.jsonl に死リンクあり (捏造または恒久 404)。\n"
        f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    )
