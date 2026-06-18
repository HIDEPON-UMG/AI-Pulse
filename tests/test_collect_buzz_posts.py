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

    rows, degraded = buzz.collect_from_rss_paths(
        str(tmp_path),
        today="2026-06-18",
        observed_at="2026-06-18T00:10:00+00:00",
    )

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
            "buzz_score": 312,
            "absolute_score": 156,
            "velocity_score": 156.0,
            "score_basis": "embedded_metrics",
            "engagement": {"likes": 120, "reposts": 18, "replies": 0, "quotes": 0},
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

    assert stats["collected"] == 1
    assert stats["written"] == 1
    assert stats["degraded"] == 0
    text = out.read_text(encoding="utf-8")
    row = json.loads(text)
    assert row["category"] == "agent"
    assert row["post_url"] == "https://x.com/example/status/222"
    assert "auth_token" not in text


def test_collect_writes_buzzpost_stats_for_threshold_diagnostics(tmp_path):
    rss = tmp_path / "buzzpost-model.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-model</title>
    <item>
      <title>Zero score</title>
      <link>https://x.com/example/status/701</link>
      <description>No metric post</description>
    </item>
    <item>
      <title>Below threshold</title>
      <link>https://x.com/example/status/702</link>
      <description>Small reaction. 8 likes 1 repost 1 reply</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )
    out = tmp_path / "buzz_posts.jsonl"
    stats_path = tmp_path / "buzz_posts_stats.json"

    stats = buzz.collect(
        rss_paths=str(rss),
        output_path=out,
        stats_path=stats_path,
        today="2026-06-18",
    )

    assert stats["candidate_count"] == 2
    assert stats["collected"] == 0
    assert stats["dropped_threshold"] == 2
    saved = json.loads(stats_path.read_text(encoding="utf-8"))
    assert saved["candidate_count"] == 2
    assert saved["dropped_threshold"] == 2
    assert saved["min_absolute_score"] == buzz.BUZZPOST_MIN_ABSOLUTE_SCORE
    assert saved["min_velocity_score"] == buzz.BUZZPOST_MIN_VELOCITY_SCORE


def test_collect_writes_stats_next_to_custom_output_by_default(tmp_path):
    rss = tmp_path / "buzzpost-agent.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-agent</title>
    <item>
      <title>Worth showing</title>
      <link>https://x.com/example/status/801</link>
      <description>Agent workflow. 30 likes 4 reposts 2 replies</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )
    out = tmp_path / "nested" / "buzz_posts.jsonl"

    buzz.collect(rss_paths=str(rss), output_path=out, today="2026-06-18")

    assert (tmp_path / "nested" / "buzz_posts_stats.json").exists()


def test_buzzpost_keeps_original_post_line_breaks_and_urls(tmp_path):
    rss = tmp_path / "buzzpost-editor.xml"
    original_text = (
        "Claude Code でここまでできる\n"
        "\n"
        "手順もそのまま残したい https://x.com/example/status/333\n"
        "Cursor との比較も追記\n"
        "likes 35 reposts 4 replies 2"
    )
    rss.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>buzzpost-editor</title>
    <item>
      <title>2026-06-18 09:10:00</title>
      <link>https://x.com/example/status/333</link>
      <content:encoded>{original_text}</content:encoded>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    rows, degraded = buzz.collect_from_rss_paths(str(tmp_path), today="2026-06-18")

    assert degraded is False
    assert rows[0]["text"] == original_text


def test_buzzpost_drops_zero_and_below_threshold_scores(tmp_path):
    rss = tmp_path / "buzzpost-model.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-model</title>
    <item>
      <title>Zero score</title>
      <link>https://x.com/example/status/401</link>
      <description>Generated AI rumor without engagement metrics</description>
    </item>
    <item>
      <title>Below threshold</title>
      <link>https://x.com/example/status/402</link>
      <description>Small reaction. likes 8 reposts 1 replies 1</description>
    </item>
    <item>
      <title>Worth showing</title>
      <link>https://x.com/example/status/403</link>
      <description>Real community signal. likes 30 reposts 4 replies 3</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    rows, degraded = buzz.collect_from_rss_paths(str(rss), today="2026-06-18")

    assert degraded is False
    assert [row["post_url"] for row in rows] == ["https://x.com/example/status/403"]
    assert rows[0]["buzz_score"] >= buzz.BUZZPOST_MIN_ABSOLUTE_SCORE


def test_buzzpost_keeps_min_faves_search_hits_without_embedded_metrics(tmp_path):
    rss = tmp_path / "buzzpost-model.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-model</title>
    <description>(Claude OR LLM) lang:ja min_faves:50 since:2026-06-08 -filter:replies</description>
    <item>
      <title>2026-06-18 09:30:00</title>
      <link>https://x.com/example/status/901</link>
      <pubDate>Thu, 18 Jun 2026 09:30:00 +0900</pubDate>
      <description>Claude Code の運用知見がかなり共有されている</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    rows, degraded = buzz.collect_from_rss_paths(str(rss), today="2026-06-18")

    assert degraded is False
    assert [row["post_url"] for row in rows] == ["https://x.com/example/status/901"]
    assert rows[0]["absolute_score"] == 50
    assert rows[0]["score_basis"] == "query_min_faves"


def test_buzzpost_excludes_ai_illustration_hashtag_even_when_score_is_high(tmp_path):
    rss = tmp_path / "buzzpost-media.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-media</title>
    <description>("画像生成AI") lang:ja min_faves:50</description>
    <item>
      <title>2026-06-18 09:30:00</title>
      <link>https://x.com/example/status/ai-illust</link>
      <description>おはようございます #AIイラスト likes 999 reposts 100</description>
      <pubDate>Thu, 18 Jun 2026 09:30:00 +0000</pubDate>
    </item>
    <item>
      <title>2026-06-18 09:40:00</title>
      <link>https://x.com/example/status/kept</link>
      <description>Sora workflow update likes 80 reposts 5</description>
      <pubDate>Thu, 18 Jun 2026 09:40:00 +0000</pubDate>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    rows, degraded = buzz.collect_from_rss_paths(str(rss), today="2026-06-18")

    assert degraded is False
    assert [row["post_url"] for row in rows] == ["https://x.com/example/status/kept"]
    assert all("#AIイラスト" not in row["text"] for row in rows)


def test_buzzpost_keeps_fast_growing_post_below_absolute_threshold(tmp_path):
    rss = tmp_path / "buzzpost-agent.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-agent</title>
    <item>
      <title>2026-06-18 09:30:00</title>
      <link>https://x.com/example/status/501</link>
      <pubDate>Thu, 18 Jun 2026 09:30:00 +0900</pubDate>
      <description>Fresh MCP workflow. 12 likes 3 reposts 2 replies</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    rows, degraded = buzz.collect_from_rss_paths(
        str(rss),
        today="2026-06-18",
        observed_at="2026-06-18T01:30:00+00:00",
    )

    assert degraded is False
    assert len(rows) == 1
    assert rows[0]["absolute_score"] < buzz.BUZZPOST_MIN_ABSOLUTE_SCORE
    assert rows[0]["velocity_score"] >= buzz.BUZZPOST_MIN_VELOCITY_SCORE


def test_load_public_rows_hides_existing_ai_illustration_hashtag_rows(tmp_path):
    path = tmp_path / "buzz_posts.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in [
                {
                    "date": "2026-06-18",
                    "post_url": "https://x.com/example/status/ai-illust",
                    "text": "朝の投稿 #AIイラスト likes 999",
                    "buzz_score": 999,
                    "absolute_score": 999,
                },
                {
                    "date": "2026-06-18",
                    "post_url": "https://x.com/example/status/kept",
                    "text": "Claude Code update likes 50",
                    "buzz_score": buzz.BUZZPOST_MIN_ABSOLUTE_SCORE,
                    "absolute_score": buzz.BUZZPOST_MIN_ABSOLUTE_SCORE,
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rows = buzz.load_public_rows(path)

    assert [row["post_url"] for row in rows] == ["https://x.com/example/status/kept"]


def test_load_public_rows_hides_existing_zero_score_rows(tmp_path):
    path = tmp_path / "buzz_posts.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in [
                {
                    "date": "2026-06-18",
                    "post_url": "https://x.com/example/status/601",
                    "buzz_score": 0,
                },
                {
                    "date": "2026-06-18",
                    "post_url": "https://x.com/example/status/602",
                    "buzz_score": buzz.BUZZPOST_MIN_ABSOLUTE_SCORE,
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rows = buzz.load_public_rows(path)

    assert [row["post_url"] for row in rows] == ["https://x.com/example/status/602"]
