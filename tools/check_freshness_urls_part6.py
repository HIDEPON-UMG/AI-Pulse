#!/usr/bin/env python3
"""鮮度レビュー Part 6 (残 15 entity) で追加予定の URL を validate_urls で一括検証する一回限りスクリプト。

200 OK / ambiguous OK のみ entities.jsonl に書ける。fatal は除外して別 URL を探すか source 名だけ残す。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from tools.validate_urls import UrlRef, verify_urls  # noqa: E402

# 鮮度更新で追加 / 流用する URL 候補
CANDIDATES: list[UrlRef] = [
    # tesla-optimus
    UrlRef("https://electrek.co/2026/04/22/tesla-optimus-production-fremont-model-sx-line/", "tesla-optimus.history.2026-04"),
    # runway
    UrlRef("https://runwayml.com/research/introducing-runway-gen-4.5", "runway.history.2025-12"),
    UrlRef("https://www.cnbc.com/2025/12/01/runway-gen-4-5-video-model-google-open-ai.html", "runway.history.2025-12.alt"),
    # langgraph
    UrlRef("https://changelog.langchain.com/announcements/langgraph-1-0-is-now-generally-available", "langgraph.history.2025"),
    # eu-ai-act
    UrlRef("https://www.lw.com/en/insights/ai-act-update-eu-resolves-to-change-rules-and-extend-deadlines", "eu-ai-act.history.2026-05"),
    UrlRef("https://www.traverssmith.com/knowledge/knowledge-container/eu-agrees-to-delay-key-ai-act-compliance-deadlines/", "eu-ai-act.history.2026-05.alt"),
    # japan-ai-act
    UrlRef("https://www.gov-online.go.jp/hlj/en/november_2025/november_2025-08.html", "japan-ai-act.history.2025-11"),
    UrlRef("https://www.whitecase.com/insight-alert/japans-first-ai-legislation-becomes-law-focus-promoting-research-and-development-no", "japan-ai-act.history.alt"),
    # figure
    UrlRef("https://www.techtimes.com/articles/316632/20260514/figure-ais-helix-02-robots-complete-full-8-hour-autonomous-shifts-humanoid-race-intensifies.htm", "figure.history.2026-05"),
    # ironwood-tpu
    UrlRef("https://newsletter.semianalysis.com/p/tpuv7-google-takes-a-swing-at-the", "ironwood-tpu.history.2026"),
    UrlRef("https://www.anthropic.com/news/expanding-our-use-of-google-cloud-tpus-and-services", "ironwood-tpu.history.anthropic"),
    # vera-rubin
    UrlRef("https://nvidianews.nvidia.com/news/vera-rubin-full-production-agentic-ai-factory", "vera-rubin.history.2026-06"),
    UrlRef("https://datacentremagazine.com/news/inside-dell-and-coreweave-world-first-vera-rubin-deployment", "vera-rubin.history.alt"),
    # cosmos
    UrlRef("https://nvidianews.nvidia.com/news/nvidia-launches-cosmos-3-the-open-frontier-foundation-model-for-physical-ai", "cosmos.history.2026-06"),
    UrlRef("https://blogs.nvidia.com/blog/cosmos-3-physical-ai-open-world-foundation-model/", "cosmos.history.2026-06.alt"),
    # openclaw
    UrlRef("https://github.com/openclaw/openclaw/releases/tag/v2026.5.7", "openclaw.history.2026-05"),
    # devin Desktop / Windsurf rebrand
    UrlRef("https://devin.ai/blog/windsurf-is-now-devin-desktop", "devin.history.2026-06.alt"),
    UrlRef("https://docs.devin.ai/release-notes/2026", "devin.history.release-notes"),
    # dify
    UrlRef("https://github.com/langgenius/dify/releases", "dify.history.2026"),
    UrlRef("https://dify.ai/blog", "dify.history.blog"),
    # flux speed upgrade
    UrlRef("https://bfl.ai/blog/flux-2", "flux.history.2026-03.speed"),
    # agentkit deprecation
    UrlRef("https://developers.openai.com/api/docs/guides/agent-builder", "agentkit.modules.future.deprecation"),
]


def main() -> int:
    print(f"Validating {len(CANDIDATES)} URLs...")
    verdicts = verify_urls(CANDIDATES, max_workers=6)
    ok = []
    fatal = []
    for v in verdicts:
        status = "OK" if v.ok else "FATAL"
        print(f"  [{status}] {v.ref.location:60s} {v.ref.url}")
        if v.detail:
            print(f"           detail: {v.detail}")
        (ok if v.ok else fatal).append(v)
    print(f"\n{len(ok)} OK / {len(fatal)} FATAL")
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
