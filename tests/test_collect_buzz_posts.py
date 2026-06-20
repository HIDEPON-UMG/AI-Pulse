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
      <content:encoded>Claude Fable frontier model reports are everywhere today. 120 likes / 18 reposts</content:encoded>
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
            "text": "Claude Fable frontier model reports are everywhere today. 120 likes / 18 reposts",
            "published_at": "2026-06-17T23:10:00+00:00",
            "buzz_score": 312,
            "absolute_score": 156,
            "relative_score": 0,
            "velocity_score": 156.0,
            "score_basis": "embedded_metrics",
            "engagement": {"likes": 120, "reposts": 18, "replies": 0, "quotes": 0},
            "author_name": "example",
            "author_handle": "@example",
            "profile_image_url": "https://unavatar.io/x/example",
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
      <title>Agentic AI workflow thread</title>
      <link>https://x.com/example/status/222</link>
      <description>New MCP workflow is getting traction. likes 120 reposts 3 replies 2</description>
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
    assert saved["min_likes"] == buzz.BUZZPOST_MIN_LIKES


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
      <description>Agentic AI MCP workflow. 130 likes 4 reposts 2 replies</description>
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
        "likes 135 reposts 4 replies 2"
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


def test_buzzpost_extracts_media_images_from_content_encoded(tmp_path):
    rss = tmp_path / "buzzpost-media.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>buzzpost-media</title>
    <item>
      <title>2026-06-18 09:10:00</title>
      <link>https://x.com/example/status/with-media</link>
      <content:encoded>Sora image generation model workflow likes 120 reposts 5&lt;br&gt;&lt;img src=&quot;https://pbs.twimg.com/media/example-one.jpg&quot;&gt;&lt;br&gt;&lt;img src=&quot;https://pbs.twimg.com/media/example-two.jpg&quot;&gt;</content:encoded>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    rows, degraded = buzz.collect_from_rss_paths(str(rss), today="2026-06-18")

    assert degraded is False
    assert rows[0]["media_urls"] == [
        "https://pbs.twimg.com/media/example-one.jpg",
        "https://pbs.twimg.com/media/example-two.jpg",
    ]
    assert "<img" not in rows[0]["text"]


def test_buzzpost_extracts_author_profile_metadata_when_rss_has_it(tmp_path):
    rss = tmp_path / "buzzpost-agent.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>buzzpost-agent</title>
    <item>
      <title>2026-06-18 09:10:00</title>
      <link>https://x.com/example/status/author</link>
      <dc:creator>Example Labs</dc:creator>
      <media:thumbnail url="https://pbs.twimg.com/profile_images/example/avatar.jpg" />
      <description>AI agents MCP workflow likes 120 reposts 5</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    rows, degraded = buzz.collect_from_rss_paths(str(rss), today="2026-06-18")

    assert degraded is False
    assert rows[0]["author_name"] == "Example Labs"
    assert rows[0]["profile_image_url"] == "https://pbs.twimg.com/profile_images/example/avatar.jpg"


def test_buzzpost_falls_back_to_unavatar_profile_image_from_handle(tmp_path):
    rss = tmp_path / "buzzpost-agent.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-agent</title>
    <item>
      <title>2026-06-18 09:10:00</title>
      <link>https://x.com/example/status/author</link>
      <author>Example Labs (@example)</author>
      <description>AI agents MCP workflow likes 120 reposts 5</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    rows, degraded = buzz.collect_from_rss_paths(str(rss), today="2026-06-18")

    assert degraded is False
    assert rows[0]["author_name"] == "Example Labs"
    assert rows[0]["profile_image_url"] == "https://unavatar.io/x/example"


def test_buzzpost_fetches_link_preview_image_from_post_urls(tmp_path):
    rss = tmp_path / "buzzpost-agent.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-agent</title>
    <item>
      <title>2026-06-18 09:10:00</title>
      <link>https://x.com/example/status/preview</link>
      <author>Example Labs (@example)</author>
      <description>AI agents MCP workflow likes 120 reposts 5 https://t.co/preview</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    def fake_request_text(url: str, *, timeout: int = 20) -> str:
        assert url == "https://t.co/preview"
        return (
            '<html><head><meta property="og:title" content="Preview title">'
            '<meta property="og:image" content="https://example.com/preview.jpg">'
            '<meta property="og:site_name" content="Example"></head></html>'
        )

    rows, degraded = buzz.collect_from_rss_paths(
        str(rss),
        today="2026-06-18",
        request_text=fake_request_text,
        fetch_link_previews=True,
    )

    assert degraded is False
    assert rows[0]["link_previews"] == [
        {
            "url": "https://t.co/preview",
            "title": "Preview title",
            "site_name": "Example",
            "image_url": "https://example.com/preview.jpg",
        }
    ]


def test_buzzpost_fetches_x_oembed_without_script_for_missing_rss_media(tmp_path):
    rss = tmp_path / "buzzpost-agent.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-agent</title>
    <item>
      <title>2026-06-18 09:10:00</title>
      <link>https://x.com/example/status/with-video</link>
      <author>Example Labs (@example)</author>
      <description>AI agents MCP video card is only present in X embed. 120 likes 5 reposts https://t.co/media</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )
    seen_urls: list[str] = []

    def fake_request_text(url: str, *, timeout: int = 20) -> str:
        seen_urls.append(url)
        assert "publish.twitter.com/oembed" in url
        return json.dumps(
            {
                "html": (
                    '<blockquote class="twitter-tweet" data-dnt="true" data-theme="dark">'
                    '<p lang="ja" dir="ltr">Video post <a href="https://t.co/media">pic.twitter.com/media</a></p>'
                    '<a href="https://x.com/example/status/with-video">June 18, 2026</a>'
                    '</blockquote><script async src="https://platform.x.com/widgets.js"></script>'
                ),
                "provider_name": "X",
            }
        )

    rows, degraded = buzz.collect_from_rss_paths(
        str(rss),
        today="2026-06-18",
        request_text=fake_request_text,
        fetch_x_embeds=True,
    )

    assert degraded is False
    assert seen_urls
    assert rows[0]["x_embed_html"].startswith('<blockquote class="twitter-tweet"')
    assert 'data-theme="dark"' in rows[0]["x_embed_html"]
    assert "pic.twitter.com/media" in rows[0]["x_embed_html"]
    assert "<script" not in rows[0]["x_embed_html"].lower()


def test_buzzpost_fetches_x_oembed_even_when_rss_media_exists(tmp_path):
    rss = tmp_path / "buzzpost-agent.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-agent</title>
    <item>
      <title>2026-06-18 09:10:00</title>
      <link>https://x.com/example/status/with-image</link>
      <author>Example Labs (@example)</author>
      <description>AI agents MCP image is present in RSS too. 120 likes 5 reposts&lt;br&gt;&lt;img src=&quot;https://pbs.twimg.com/media/example.jpg&quot;&gt;</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    def fake_request_text(url: str, *, timeout: int = 20) -> str:
        assert "publish.twitter.com/oembed" in url
        return json.dumps(
            {
                "html": (
                    '<blockquote class="twitter-tweet" data-dnt="true" data-theme="dark">'
                    '<p lang="ja" dir="ltr">Image post</p>'
                    '<a href="https://x.com/example/status/with-image">June 18, 2026</a>'
                    "</blockquote>"
                ),
                "provider_name": "X",
            }
        )

    rows, degraded = buzz.collect_from_rss_paths(
        str(rss),
        today="2026-06-18",
        request_text=fake_request_text,
        fetch_x_embeds=True,
    )

    assert degraded is False
    assert rows[0]["media_urls"] == ["https://pbs.twimg.com/media/example.jpg"]
    assert rows[0]["x_embed_html"].startswith('<blockquote class="twitter-tweet"')


def test_buzzpost_translates_english_posts_and_keeps_original_for_toggle(tmp_path):
    rss = tmp_path / "buzzpost-model.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-model</title>
    <item>
      <title>2026-06-18 09:10:00</title>
      <link>https://x.com/example/status/english</link>
      <author>Example Labs (@example)</author>
      <description>Claude Fable frontier model reports are everywhere today. 120 likes 5 reposts</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    rows, degraded = buzz.collect_from_rss_paths(
        str(rss),
        today="2026-06-18",
        translate_text_ja=lambda text: "Claude Fable frontier model の報告が今日は至るところにあります。",
    )

    assert degraded is False
    assert rows[0]["text_original"] == "Claude Fable frontier model reports are everywhere today. 120 likes 5 reposts"
    assert rows[0]["text"] == "Claude Fable frontier model の報告が今日は至るところにあります。"
    assert rows[0]["translated"] is True
    assert rows[0]["engagement"]["likes"] == 120


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
      <description>Claude Fable model real community signal. likes 130 reposts 4 replies 3</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    rows, degraded = buzz.collect_from_rss_paths(str(rss), today="2026-06-18")

    assert degraded is False
    assert [row["post_url"] for row in rows] == ["https://x.com/example/status/403"]
    assert rows[0]["engagement"]["likes"] >= buzz.BUZZPOST_MIN_LIKES


def test_buzzpost_keeps_min_faves_search_hits_without_embedded_metrics(tmp_path):
    rss = tmp_path / "buzzpost-model.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-model</title>
    <description>(Claude OR LLM) lang:ja min_faves:100 since:2026-06-08 -filter:replies</description>
    <item>
      <title>2026-06-18 09:30:00</title>
      <link>https://x.com/example/status/901</link>
      <pubDate>Thu, 18 Jun 2026 09:30:00 +0900</pubDate>
      <description>Claude Fable モデルの運用知見がかなり共有されている</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    rows, degraded = buzz.collect_from_rss_paths(str(rss), today="2026-06-18")

    assert degraded is False
    assert [row["post_url"] for row in rows] == ["https://x.com/example/status/901"]
    assert rows[0]["absolute_score"] == 100
    assert rows[0]["score_basis"] == "query_min_faves"


def test_buzzpost_excludes_generic_daily_genai_usage_even_when_min_faves_query(tmp_path):
    rss = tmp_path / "buzzpost-model-ja.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>buzzpost-model-ja</title>
    <description>("LLM" OR "Claude Fable") lang:ja min_faves:100 since:2026-06-08 -filter:replies</description>
    <item>
      <title>2026-06-18 09:30:00</title>
      <link>https://x.com/example/status/generic</link>
      <pubDate>Thu, 18 Jun 2026 09:30:00 +0900</pubDate>
      <content:encoded>おはようございます。最近いろいろ生成AIに教わりながら仕事するようになってきました。生成AI込みで仕事のパフォーマンス上げていきますー https://t.co/game</content:encoded>
    </item>
    <item>
      <title>2026-06-18 09:35:00</title>
      <link>https://x.com/example/status/fable</link>
      <pubDate>Thu, 18 Jun 2026 09:35:00 +0900</pubDate>
      <content:encoded>Claude Fable と Mythos のアクセス制限で frontier model の安全性議論が加速している</content:encoded>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    rows, degraded = buzz.collect_from_rss_paths(str(rss), today="2026-06-18")

    assert degraded is False
    assert [row["post_url"] for row in rows] == ["https://x.com/example/status/fable"]
    assert rows[0]["source"] == "x-rss:buzzpost-model-ja"
    assert rows[0]["category"] == "model"


def test_buzzpost_excludes_ambiguous_short_terms_without_ai_context(tmp_path):
    media_rss = tmp_path / "buzzpost-media-ja.xml"
    agent_rss = tmp_path / "buzzpost-agent-ja.xml"
    media_rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-media-ja</title>
    <description>("Sora" OR "動画生成AI") lang:ja min_faves:100</description>
    <item>
      <title>2026-06-19 09:10:00</title>
      <link>https://x.com/example/status/sora-stage</link>
      <description>鹿児島空港「航空展示室 SORA STAGE」にて。120 likes 5 reposts</description>
    </item>
    <item>
      <title>2026-06-19 09:12:00</title>
      <link>https://x.com/example/status/sora-kun</link>
      <description>サッカ用に描いたsoraくんさん。120 likes 5 reposts</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )
    agent_rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-agent-ja</title>
    <description>("MCP" OR "AIエージェント") lang:ja min_faves:100</description>
    <item>
      <title>2026-06-19 09:14:00</title>
      <link>https://x.com/example/status/game-mcp</link>
      <description>UE5.8のMCPのテスト。Cableアクター600本で接続。120 likes 5 reposts</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    rows, degraded = buzz.collect_from_rss_paths(str(tmp_path), today="2026-06-19")

    assert degraded is False
    assert rows == []


def test_buzzpost_keeps_english_agentic_trend_post_and_translates(tmp_path):
    rss = tmp_path / "buzzpost-agent-en.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-agent-en</title>
    <description>("AI Control Roadmap" OR "agentic AI") lang:en min_faves:100 since:2026-06-08 -filter:replies</description>
    <item>
      <title>2026-06-18 09:30:00</title>
      <link>https://x.com/example/status/roadmap</link>
      <pubDate>Thu, 18 Jun 2026 09:30:00 +0000</pubDate>
      <description>Google DeepMind AI Control Roadmap is a big deal for agentic AI safety and coding agents. 120 likes 12 reposts</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    rows, degraded = buzz.collect_from_rss_paths(
        str(rss),
        today="2026-06-18",
        translate_text_ja=lambda text: "Google DeepMind の AI Control Roadmap は agentic AI safety の重要トレンドです。",
    )

    assert degraded is False
    assert len(rows) == 1
    assert rows[0]["category"] == "agent"
    assert rows[0]["translated"] is True
    assert "AI Control Roadmap" in rows[0]["text_original"]


def test_collect_preserves_same_post_url_across_observation_dates(tmp_path):
    rss = tmp_path / "buzzpost-model.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-model</title>
    <description>(Claude OR LLM) lang:ja min_faves:100</description>
    <item>
      <title>2026-06-18 09:30:00</title>
      <link>https://x.com/example/status/repeat</link>
      <pubDate>Thu, 18 Jun 2026 09:30:00 +0900</pubDate>
      <description>Claude Fable モデルの運用知見が共有されている</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )
    out = tmp_path / "buzz_posts.jsonl"
    out.write_text(
        json.dumps(
            {
                "date": "2026-06-17",
                "category": "model",
                "post_url": "https://x.com/example/status/repeat",
                "text": "Claude Fable yesterday observation",
                "buzz_score": 70,
                "absolute_score": 50,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    buzz.collect(rss_paths=str(rss), output_path=out, today="2026-06-18")
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]

    assert [
        (row["date"], row["post_url"])
        for row in rows
        if row["post_url"] == "https://x.com/example/status/repeat"
    ] == [("2026-06-18", "https://x.com/example/status/repeat")]


def test_buzzpost_adds_relative_score_for_min_faves_ties(tmp_path):
    rss = tmp_path / "buzzpost-model.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-model</title>
    <description>(Claude OR LLM) lang:ja min_faves:100 since:2026-06-08 -filter:replies</description>
    <item>
      <title>2026-06-18 09:50:00</title>
      <link>https://x.com/example/status/fast</link>
      <pubDate>Thu, 18 Jun 2026 09:50:00 +0900</pubDate>
      <description>Claude Fable モデルの新しい運用知見</description>
    </item>
    <item>
      <title>2026-06-18 06:00:00</title>
      <link>https://x.com/example/status/slow</link>
      <pubDate>Thu, 18 Jun 2026 06:00:00 +0900</pubDate>
      <description>LLM benchmark ワークフローの共有</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    rows, degraded = buzz.collect_from_rss_paths(
        str(rss),
        today="2026-06-18",
        observed_at="2026-06-18T01:00:00+00:00",
    )

    assert degraded is False
    assert [row["post_url"] for row in rows] == [
        "https://x.com/example/status/fast",
        "https://x.com/example/status/slow",
    ]
    assert {row["absolute_score"] for row in rows} == {100}
    assert rows[0]["relative_score"] > rows[1]["relative_score"]
    assert rows[0]["buzz_score"] > rows[1]["buzz_score"]


def test_buzzpost_excludes_ai_illustration_hashtag_even_when_score_is_high(tmp_path):
    rss = tmp_path / "buzzpost-media.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-media</title>
    <description>("画像生成AI") lang:ja min_faves:100</description>
    <item>
      <title>2026-06-18 09:30:00</title>
      <link>https://x.com/example/status/ai-illust</link>
      <description>おはようございます #AIイラスト likes 999 reposts 100</description>
      <pubDate>Thu, 18 Jun 2026 09:30:00 +0000</pubDate>
    </item>
    <item>
      <title>2026-06-18 09:40:00</title>
      <link>https://x.com/example/status/kept</link>
      <description>OpenAI Sora video generation workflow update likes 120 reposts 5</description>
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


def test_buzzpost_excludes_illustrator_keyword_even_when_score_is_high(tmp_path):
    rss = tmp_path / "buzzpost-media.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>buzzpost-media</title>
    <description>("画像生成AI") lang:ja min_faves:100</description>
    <item>
      <title>2026-06-18 09:30:00</title>
      <link>https://x.com/example/status/illustrator</link>
      <description>生成AIと絵師の対立話題 likes 999 reposts 100</description>
      <pubDate>Thu, 18 Jun 2026 09:30:00 +0000</pubDate>
    </item>
    <item>
      <title>2026-06-18 09:40:00</title>
      <link>https://x.com/example/status/kept</link>
      <description>OpenAI Sora video generation workflow update likes 120 reposts 5</description>
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
    assert all("絵師" not in row["text"] for row in rows)


def test_buzzpost_drops_fast_growing_post_below_like_threshold(tmp_path):
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
      <description>Fresh MCP server workflow for AI agents. 12 likes 3 reposts 2 replies</description>
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
    assert rows == []


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
                    "category": "editor",
                    "text": "Claude Code update likes 120",
                    "buzz_score": buzz.BUZZPOST_MIN_LIKES,
                    "absolute_score": buzz.BUZZPOST_MIN_LIKES,
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
                    "category": "model",
                    "text": "Claude Fable update likes 120",
                    "buzz_score": buzz.BUZZPOST_MIN_LIKES,
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rows = buzz.load_public_rows(path)

    assert [row["post_url"] for row in rows] == ["https://x.com/example/status/602"]


def test_load_public_rows_retains_only_latest_seven_calendar_days(tmp_path):
    path = tmp_path / "buzz_posts.jsonl"
    rows = []
    for day in range(1, 10):
        date = f"2026-06-{day:02d}"
        rows.append(
            {
                "date": date,
                "post_url": f"https://x.com/example/status/{day}",
                "category": "model",
                "text": f"Claude Fable frontier model BuzzPost {day} likes 120",
                "buzz_score": buzz.BUZZPOST_MIN_LIKES,
                "absolute_score": buzz.BUZZPOST_MIN_LIKES,
            }
        )
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    loaded = buzz.load_public_rows(path)

    assert {row["date"] for row in loaded} == {
        "2026-06-03",
        "2026-06-04",
        "2026-06-05",
        "2026-06-06",
        "2026-06-07",
        "2026-06-08",
        "2026-06-09",
    }


def test_collect_writes_only_latest_seven_calendar_days(tmp_path):
    output = tmp_path / "buzz_posts.jsonl"
    existing = []
    for day in range(1, 9):
        date = f"2026-06-{day:02d}"
        existing.append(
            {
                "date": date,
                "post_url": f"https://x.com/example/status/existing-{day}",
                "category": "model",
                "text": f"Claude Fable frontier model Existing BuzzPost {day} likes 120",
                "buzz_score": buzz.BUZZPOST_MIN_LIKES,
                "absolute_score": buzz.BUZZPOST_MIN_LIKES,
            }
        )
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in existing),
        encoding="utf-8",
    )
    rss = tmp_path / "buzzpost-model.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>buzzpost-model</title>
    <description>(GPT-5 OR Claude) lang:ja min_faves:100</description>
    <item>
      <title>2026-06-09 09:00:00</title>
      <link>https://x.com/example/status/new-9</link>
      <pubDate>Tue, 09 Jun 2026 09:00:00 +0900</pubDate>
      <content:encoded>Claude Fable model update likes 120</content:encoded>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    buzz.collect(
        rss_paths=str(rss),
        output_path=output,
        today="2026-06-09",
        observed_at="2026-06-09T09:30:00+09:00",
        fetch_link_previews=False,
        fetch_x_embeds=False,
        translate_text_ja=lambda text: text,
    )

    written = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert {row["date"] for row in written} == {
        "2026-06-03",
        "2026-06-04",
        "2026-06-05",
        "2026-06-06",
        "2026-06-07",
        "2026-06-08",
        "2026-06-09",
    }
