from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import collect_buzz_posts as buzz  # noqa: E402


def test_buzzpost_rss_extracts_ai_category_posts(tmp_path):
    rss = tmp_path / "buzzpost-model.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>buzzpost-model</title>
    <description>(GPT-5 OR Claude OR Gemini) lang:en</description>
    <item>
      <title>2026-06-18 08:10:00</title>
      <link>https://x.com/example/status/111</link>
      <pubDate>Thu, 18 Jun 2026 08:10:00 +0900</pubDate>
      <content:encoded>Claude Code agents are everywhere today. 120 likes / 18 reposts</content:encoded>
    </item>
    <item>
      <title>No URL</title>
      <content:encoded>missing link should be ignored</content:encoded>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    rows, degraded = buzz.collect_from_rss_paths(str(tmp_path), today="2026-06-18")

    assert degraded is False
    assert rows == [
        {
            "date": "2026-06-18",
            "category": "model",
            "category_label": "モデル/LLM",
            "glyph": "◆",
            "source": "x-rss:buzzpost-model",
            "source_query": "(GPT-5 OR Claude OR Gemini) lang:en",
            "post_url": "https://x.com/example/status/111",
            "title": "2026-06-18 08:10:00",
            "text": "Claude Code agents are everywhere today. 120 likes / 18 reposts",
            "published_at": "2026-06-17T23:10:00+00:00",
            "buzz_score": 156,
        }
    ]


def test_collect_writes_public_buzzpost_jsonl(tmp_path):
    rss = tmp_path / "buzzpost-agent.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-agent</title>
    <description>(agent OR MCP) lang:en</description>
    <item>
      <title>Agent workflow thread</title>
      <link>https://x.com/example/status/222</link>
      <description>New MCP workflow is getting traction. likes 20 reposts 3 replies 2</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )
    out = tmp_path / "buzz_posts.jsonl"

    stats = buzz.collect(rss_paths=str(rss), output_path=out, today="2026-06-18")

    assert stats == {"collected": 1, "written": 1, "degraded": 0}
    text = out.read_text(encoding="utf-8")
    row = json.loads(text)
    assert row["category"] == "agent"
    assert row["post_url"] == "https://x.com/example/status/222"
    assert "auth_token" not in text
