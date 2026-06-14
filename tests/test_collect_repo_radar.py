import json
import ast
from pathlib import Path

import pytest

from tools import collect_repo_radar as radar
from tools import llm_local


def test_extract_github_repos_normalizes_and_skips_non_repo_urls():
    text = (
        "https://github.com/openai/codex and "
        "https://github.com/openai/codex/issues/1 plus "
        "https://github.com/modelcontextprotocol/servers)"
    )
    assert radar.extract_github_repos(text) == [
        "openai/codex",
        "modelcontextprotocol/servers",
    ]


def test_module_import_does_not_require_llm_backend_dependencies():
    """Pages 生成時の import では Gemini/Ollama 評価用依存を読まない。"""
    source = Path("tools/collect_repo_radar.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level_imports = [
        alias.name
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    ]

    assert "llm_local" not in top_level_imports


def test_extract_github_repos_accepts_x_mangled_urls():
    text = (
        "hxxps://github.com/DataDog/guarddog/blob/main/tests "
        "https ://github.com/libass/libass "
        "-/github.com/thesysdev/openui "
        "https://github.com/acme/example.git"
    )
    assert radar.extract_github_repos(text) == [
        "DataDog/guarddog",
        "libass/libass",
        "thesysdev/openui",
        "acme/example",
    ]


def test_merge_signals_combines_reddit_and_hn_for_same_repo():
    merged = radar.merge_signals([
        {
            "source": "hn",
            "title": "Show HN: Codex",
            "url": "https://github.com/openai/codex",
            "points": 120,
            "comments": 30,
        },
        {
            "source": "reddit:ClaudeCode",
            "title": "Codex workflow",
            "url": "https://github.com/OpenAI/codex",
            "points": 50,
            "comments": 8,
        },
    ])
    item = merged["openai/codex"]
    assert item["repo"] == "openai/codex"
    assert len(item["sources"]) == 2
    assert item["score_hint"] == 208


def test_reddit_without_oauth_is_degraded_not_error(monkeypatch):
    monkeypatch.delenv("REDDIT_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("REDDIT_USER_AGENT", raising=False)
    items, degraded = radar.fetch_reddit_candidates(request_json=lambda *_args, **_kwargs: {})
    assert items == []
    assert degraded is True


def test_reddit_uses_client_credentials_when_bearer_is_absent(monkeypatch):
    monkeypatch.delenv("REDDIT_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("REDDIT_CLIENT_ID", "client")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")
    monkeypatch.setenv("REDDIT_USER_AGENT", "windows:ai-pulse-repo-radar:v0.1 (by /u/example)")
    monkeypatch.setattr(radar, "_fetch_reddit_token", lambda _ua: "issued-token")
    seen_headers = []

    def fake_request_json(_url, **kwargs):
        seen_headers.append(kwargs.get("headers") or {})
        return {"data": {"children": []}}

    items, degraded = radar.fetch_reddit_candidates(request_json=fake_request_json, limit=1)
    assert items == []
    assert degraded is False
    assert seen_headers
    assert seen_headers[0]["Authorization"] == "Bearer issued-token"


def test_x_without_bearer_is_degraded_not_error(monkeypatch):
    monkeypatch.setenv("REPO_RADAR_ENABLE_X", "1")
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    items, degraded = radar.fetch_x_candidates(request_json=lambda *_args, **_kwargs: {})
    assert items == []
    assert degraded is True


def test_x_requires_explicit_enable_even_with_bearer(monkeypatch):
    monkeypatch.delenv("REPO_RADAR_ENABLE_X", raising=False)
    monkeypatch.setenv("X_BEARER_TOKEN", "x-token")
    called = False

    def fake_request_json(*_args, **_kwargs):
        nonlocal called
        called = True
        return {}

    items, degraded = radar.fetch_x_candidates(request_json=fake_request_json)
    assert items == []
    assert degraded is False
    assert called is False


def test_x_rss_candidates_parse_twitter_rss_output(tmp_path):
    rss = tmp_path / "repo-radar.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>repo-radar</title>
    <item>
      <title>Useful MCP repo</title>
      <link>https://x.com/example/status/12345</link>
      <description>Try https://github.com/acme/mcp-tool for agents.</description>
    </item>
    <item>
      <title>No repo here</title>
      <link>https://x.com/example/status/67890</link>
      <description>Just text.</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )
    items, degraded = radar.fetch_x_rss_candidates(rss_paths=str(tmp_path))
    assert degraded is False
    assert items == [
        {
            "source": "x-rss:repo-radar",
            "title": "Useful MCP repo",
            "url": "https://x.com/example/status/12345",
            "text": "Try https://github.com/acme/mcp-tool for agents.",
            "points": 0,
            "comments": 0,
        }
    ]


def test_x_rss_candidates_parse_content_encoded(tmp_path):
    rss = tmp_path / "repo-radar.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <item>
      <title>2026-06-13 10:00:00</title>
      <link>https://twitter.com/example/status/2</link>
      <content:encoded>hxxps://github.com/acme/mangled-repo is useful.</content:encoded>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )
    items, degraded = radar.fetch_x_rss_candidates(rss_paths=str(rss))
    assert degraded is False
    assert radar.merge_signals(items)["acme/mangled-repo"]["repo"] == "acme/mangled-repo"


def test_x_rss_candidates_skip_stale_items(tmp_path):
    rss = tmp_path / "repo-radar.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <item>
      <title>2000-01-01 00:00:00</title>
      <link>https://twitter.com/example/status/old</link>
      <content:encoded>https://github.com/acme/old-repo</content:encoded>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )
    items, degraded = radar.fetch_x_rss_candidates(rss_paths=str(rss))
    assert degraded is False
    assert items == []


def test_x_recent_search_extracts_github_signal(monkeypatch):
    monkeypatch.setenv("REPO_RADAR_ENABLE_X", "1")
    monkeypatch.setenv("X_BEARER_TOKEN", "x-token")
    monkeypatch.setenv("REPO_RADAR_X_QUERIES", "github.com MCP lang:en")
    seen = {}

    def fake_request_json(url, **kwargs):
        seen["url"] = url
        seen["headers"] = kwargs.get("headers") or {}
        return {
            "data": [
                {
                    "id": "12345",
                    "text": "This MCP repo looks useful https://github.com/acme/mcp-tool",
                    "public_metrics": {
                        "like_count": 10,
                        "retweet_count": 2,
                        "quote_count": 1,
                        "reply_count": 3,
                    },
                }
            ]
        }

    items, degraded = radar.fetch_x_candidates(request_json=fake_request_json, limit=10)
    assert degraded is False
    assert items == [
        {
            "source": "x",
            "title": "This MCP repo looks useful https://github.com/acme/mcp-tool",
            "url": "https://x.com/i/web/status/12345",
            "text": "This MCP repo looks useful https://github.com/acme/mcp-tool",
            "points": 16,
            "comments": 3,
        }
    ]
    assert "tweets/search/recent" in seen["url"]
    assert seen["headers"]["Authorization"] == "Bearer x-token"


def test_github_backfill_candidates_search_recent_popular_repos(monkeypatch):
    monkeypatch.setenv("REPO_RADAR_BACKFILL_QUERIES", "agentic coding\nmcp server")
    seen_urls = []

    def fake_request_json(url, **kwargs):
        seen_urls.append(url)
        assert kwargs["headers"]["User-Agent"] == "AI-Pulse-Repo-Radar/0.1"
        return {
            "items": [
                {
                    "full_name": "acme/agent-tool",
                    "html_url": "https://github.com/acme/agent-tool",
                    "description": "Agentic coding helper",
                    "stargazers_count": 1234,
                    "forks_count": 56,
                    "topics": ["agents", "coding"],
                    "language": "Python",
                    "created_at": "2026-04-01T00:00:00Z",
                    "pushed_at": "2026-06-14T00:00:00Z",
                },
                {
                    "full_name": "acme/agent-tool",
                    "html_url": "https://github.com/acme/agent-tool",
                    "description": "duplicate",
                    "stargazers_count": 1200,
                    "forks_count": 50,
                },
            ]
        }

    items, degraded = radar.fetch_github_backfill_candidates(
        request_json=fake_request_json,
        days=90,
        per_query_limit=2,
        max_items=3,
        today="2026-06-15",
    )
    assert degraded is False
    assert len(seen_urls) == 2
    assert "created:%3E=2026-03-17" in seen_urls[0]
    assert items == [
        {
            "source": "github-backfill:90d",
            "title": "acme/agent-tool",
            "url": "https://github.com/acme/agent-tool",
            "text": "Agentic coding helper topics=agents,coding language=Python created_at=2026-04-01T00:00:00Z pushed_at=2026-06-14T00:00:00Z",
            "points": 1234,
            "comments": 56,
        }
    ]


def test_ollama_eval_validates_schema_and_retries_once(monkeypatch):
    monkeypatch.setattr(radar.config, "OLLAMA_MAX_RETRIES", 1)
    calls = []

    def fake_call(_prompt, _schema):
        calls.append(1)
        if len(calls) == 1:
            return {"summary": "missing required fields"}
        return {
            "summary": "AI コーディング支援の小型ツールです。",
            "feature_outline": [
                {"lens": "Capability", "text": "小型の支援機能を提供します。"},
            ],
            "developer_use_case": "日次調査と実装補助に使えます。",
            "implementation_difficulty": "medium: 設定が必要です。",
            "pricing_or_license": "MIT",
            "adoption_reason": "運用適合性: 日次運用へ段階導入しやすいため。",
            "ai_pulse_fit": ["収集基盤"],
            "ideastash_fit_public": ["エージェント運用"],
            "risk_notes": ["保守状況を確認してください"],
            "score": 72,
        }

    payload = radar._ollama_chat_json(
        {"repo": "openai/codex", "readme_excerpt": "README"},
        {"sources": []},
        [],
        call_once=fake_call,
    )
    assert payload["score"] == 72
    assert len(calls) == 2


def test_ollama_eval_failure_is_reported_as_llm_error(monkeypatch):
    monkeypatch.setattr(radar.config, "OLLAMA_MAX_RETRIES", 0)
    with pytest.raises(llm_local.LLMError):
        radar._ollama_chat_json(
            {"repo": "openai/codex", "readme_excerpt": "README"},
            {"sources": []},
            [],
            call_once=lambda *_args: {"summary": "bad"},
        )


def test_collect_writes_public_anonymized_data_and_private_matches(tmp_path, monkeypatch):
    ideas = tmp_path / "ideas"
    ideas.mkdir()
    (ideas / "SecretTask-mobile-copy-2026-06-01.md").write_text(
        """---
title: スマホのコピーボタン修正
status: stash
score: 120
tags:
  - artifact
implementation_outline:
  - Clipboard API を直す
---
""",
        encoding="utf-8",
    )

    def fake_request_json(url, **_kwargs):
        if url.endswith("topstories.json"):
            return [1]
        if url.endswith("beststories.json") or url.endswith("showstories.json") or url.endswith("newstories.json"):
            return []
        if url.endswith("/item/1.json"):
            return {
                "title": "Show HN: Useful repo",
                "url": "https://github.com/acme/useful-repo",
                "score": 90,
                "descendants": 12,
            }
        if url.endswith("/repos/acme/useful-repo"):
            return {
                "html_url": "https://github.com/acme/useful-repo",
                "name": "useful-repo",
                "description": "Useful repo",
                "homepage": "",
                "language": "Python",
                "license": {"spdx_id": "MIT"},
                "topics": ["ai"],
                "stargazers_count": 100,
                "forks_count": 5,
                "open_issues_count": 2,
                "created_at": "2026-06-01T00:00:00Z",
                "pushed_at": "2026-06-13T00:00:00Z",
            }
        if url.endswith("/readme"):
            return {"encoding": "base64", "content": "UkVBRE1F"}
        raise RuntimeError(url)

    def fake_eval(_prompt, _schema):
        return {
            "summary": "AI 開発の補助ツールです。",
            "feature_outline": [
                {"lens": "Capability", "text": "調査補助を自動化します。"},
                {"lens": "Activation", "text": "Python で小さく導入できます。"},
            ],
            "developer_use_case": "実装前調査に使えます。",
            "implementation_difficulty": "easy: Python だけで試せます。",
            "pricing_or_license": "MIT",
            "adoption_reason": "運用適合性: 収集基盤に低コストで接続できるため。",
            "ai_pulse_fit": ["収集基盤"],
            "ideastash_fit_public": ["UI/UX 改善"],
            "risk_notes": ["スター数だけで判断しないでください"],
            "score": 88,
        }

    monkeypatch.delenv("REDDIT_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("REPO_RADAR_X_RSS_PATHS", raising=False)
    out = tmp_path / "repo_radar.jsonl"
    stats = radar.collect(
        request_json=fake_request_json,
        eval_call_once=fake_eval,
        output_path=out,
        log_dir=tmp_path,
        ideas_dir=ideas,
        today="2026-06-13",
    )
    assert stats["evaluated"] == 1
    public_text = out.read_text(encoding="utf-8")
    assert "SecretTask" not in public_text
    assert "スマホのコピーボタン修正" not in public_text
    assert r"C:\Users\hidek\Obsidian\IdeaStash" not in public_text
    row = json.loads(public_text)
    assert row["repo"] == "acme/useful-repo"
    assert row["created_at"] == "2026-06-01T00:00:00Z"
    assert row["thumbnail_url"] == "https://opengraph.githubassets.com/ai-pulse/acme/useful-repo"
    assert row["feature_outline"][0]["lens"] == "Capability"
    assert row["adoption_reason"].startswith("運用適合性")
    assert row["ideastash_fit_public"] == ["UI/UX 改善"]
    private_text = (tmp_path / "repo_radar_matches_20260613.jsonl").read_text(encoding="utf-8")
    assert "SecretTask-mobile-copy-2026-06-01.md" in private_text
    assert "スマホのコピーボタン修正" in private_text


def test_collect_includes_backfill_only_when_requested(tmp_path, monkeypatch):
    def fake_backfill(**_kwargs):
        return ([
            {
                "source": "github-backfill:180d",
                "title": "acme/backfill-repo",
                "url": "https://github.com/acme/backfill-repo",
                "text": "Backfill repo",
                "points": 900,
                "comments": 25,
            }
        ], False)

    def fake_request_json(url, **_kwargs):
        if url.endswith("topstories.json") or url.endswith("beststories.json"):
            return []
        if url.endswith("showstories.json") or url.endswith("newstories.json"):
            return []
        if url.endswith("/repos/acme/backfill-repo"):
            return {
                "html_url": "https://github.com/acme/backfill-repo",
                "name": "backfill-repo",
                "description": "Backfill repo",
                "homepage": "",
                "language": "TypeScript",
                "license": {"spdx_id": "Apache-2.0"},
                "topics": ["agent"],
                "stargazers_count": 900,
                "forks_count": 25,
                "open_issues_count": 3,
                "created_at": "2026-02-01T00:00:00Z",
                "pushed_at": "2026-06-14T00:00:00Z",
            }
        if url.endswith("/readme"):
            return {"encoding": "base64", "content": "UkVBRE1F"}
        raise RuntimeError(url)

    def fake_eval(_prompt, _schema):
        return {
            "summary": "AI 開発を支援するバックフィル候補です。",
            "feature_outline": [{"lens": "Capability", "text": "開発作業を補助します。"}],
            "developer_use_case": "エージェント開発の補助に使えます。",
            "implementation_difficulty": "medium: 導入設定が必要です。",
            "pricing_or_license": "Apache-2.0",
            "adoption_reason": "運用適合性: 初回在庫として評価する価値が高いため。",
            "ai_pulse_fit": ["Repo Radar"],
            "ideastash_fit_public": ["エージェント運用"],
            "risk_notes": ["過去急伸候補なので現在の保守状況を確認してください"],
            "score": 84,
        }

    monkeypatch.setattr(radar, "fetch_github_backfill_candidates", fake_backfill)
    monkeypatch.delenv("REDDIT_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("REPO_RADAR_X_RSS_PATHS", raising=False)

    out = tmp_path / "repo_radar.jsonl"
    stats = radar.collect(
        request_json=fake_request_json,
        eval_call_once=fake_eval,
        output_path=out,
        log_dir=tmp_path,
        today="2026-06-15",
        backfill_days=180,
        max_candidates=5,
        max_enrich=5,
        max_evaluate=1,
    )

    assert stats["evaluated"] == 1
    assert stats["backfill_candidates"] == 1
    row = json.loads(out.read_text(encoding="utf-8"))
    assert row["repo"] == "acme/backfill-repo"
    assert row["signals"][0]["source"] == "github-backfill:180d"


def test_collect_skips_repos_already_in_public_rows(tmp_path, monkeypatch):
    def fake_backfill(**_kwargs):
        return ([
            {
                "source": "github-backfill:180d",
                "title": "acme/existing-repo",
                "url": "https://github.com/acme/existing-repo",
                "text": "Already known",
                "points": 1000,
                "comments": 10,
            },
            {
                "source": "github-backfill:180d",
                "title": "acme/new-repo",
                "url": "https://github.com/acme/new-repo",
                "text": "New repo",
                "points": 900,
                "comments": 9,
            },
        ], False)

    def fake_request_json(url, **_kwargs):
        if url.endswith("topstories.json") or url.endswith("beststories.json"):
            return []
        if url.endswith("showstories.json") or url.endswith("newstories.json"):
            return []
        if url.endswith("/repos/acme/new-repo"):
            return {
                "html_url": "https://github.com/acme/new-repo",
                "name": "new-repo",
                "description": "New repo",
                "homepage": "",
                "language": "Python",
                "license": {"spdx_id": "MIT"},
                "topics": ["agent"],
                "stargazers_count": 900,
                "forks_count": 9,
                "open_issues_count": 1,
                "created_at": "2026-03-01T00:00:00Z",
                "pushed_at": "2026-06-14T00:00:00Z",
            }
        if url.endswith("/readme"):
            return {"encoding": "base64", "content": "UkVBRE1F"}
        raise RuntimeError(url)

    def fake_eval(_prompt, _schema):
        return {
            "summary": "新規 repo だけを評価します。",
            "feature_outline": [{"lens": "Capability", "text": "重複を避けます。"}],
            "developer_use_case": "バックフィルの小分け実行に使えます。",
            "implementation_difficulty": "easy: 追加設定は不要です。",
            "pricing_or_license": "MIT",
            "adoption_reason": "運用適合性: 既存候補の再評価を避けられるため。",
            "ai_pulse_fit": ["Repo Radar"],
            "ideastash_fit_public": ["エージェント運用"],
            "risk_notes": ["重複除外後の候補数を確認してください"],
            "score": 80,
        }

    out = tmp_path / "repo_radar.jsonl"
    out.write_text(json.dumps({"date": "2026-06-14", "repo": "acme/existing-repo"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(radar, "fetch_github_backfill_candidates", fake_backfill)
    monkeypatch.delenv("REDDIT_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("REPO_RADAR_X_RSS_PATHS", raising=False)

    stats = radar.collect(
        request_json=fake_request_json,
        eval_call_once=fake_eval,
        output_path=out,
        log_dir=tmp_path,
        today="2026-06-15",
        backfill_days=180,
        max_candidates=5,
        max_enrich=5,
        max_evaluate=2,
    )

    assert stats["evaluated"] == 1
    repos = [json.loads(line)["repo"] for line in out.read_text(encoding="utf-8").splitlines()]
    assert "acme/existing-repo" in repos
    assert "acme/new-repo" in repos
