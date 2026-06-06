"""AI-Pulse pytest 共通設定 (Plan v3 P2)。

- `network` marker を定義 (`-m "not network"` で外部 HTTP test を一括除外)。
- 移行期後方互換: `AI_PULSE_SKIP_URL_CHECK=1` が立っていれば network marker
  test を自動 skip。安定後の環境変数廃止は別タスク。

> 由来: Plan v3 (`~/.claude/plans/quiet-foraging-floyd.md`) P2 横展開。
> News-Grasp の同等 conftest と pair で動かす。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "network: 外部 HTTP を実打鍵する test (CI/オフラインでは "
        "`-m \"not network\"` で除外、ローカルで `-m network` で個別実行)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if os.environ.get("AI_PULSE_SKIP_URL_CHECK") != "1":
        return
    skip_network = pytest.mark.skip(
        reason="AI_PULSE_SKIP_URL_CHECK=1 で network test を skip (移行期互換)"
    )
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)
