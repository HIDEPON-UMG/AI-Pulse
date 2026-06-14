import json
from pathlib import Path

from tools import repo_radar_obsidian as obsidian


def _repo_row(repo: str = "acme/useful-repo") -> dict:
    return {
        "date": "2026-06-13",
        "repo": repo,
        "repo_url": f"https://github.com/{repo}",
        "name": repo.split("/")[-1],
        "description": "Useful repo",
        "language": "Python",
        "license": "MIT",
        "topics": ["ai", "mcp", "automation"],
        "stars": 1234,
        "forks": 12,
        "open_issues": 3,
        "created_at": "2026-06-01T00:00:00Z",
        "pushed_at": "2026-06-13T00:00:00Z",
        "score": 88,
        "summary": "AI 開発の補助ツールです。",
        "feature_outline": [
            {"lens": "Capability", "text": "調査補助を自動化します。"},
            {"lens": "Reuse", "text": "MCP 連携の参考実装になります。"},
        ],
        "developer_use_case": "実装前調査に使えます。",
        "implementation_difficulty": "easy: Python だけで試せます。",
        "pricing_or_license": "MIT",
        "adoption_reason": "運用適合性: 収集基盤に低コストで接続できるため。",
        "ai_pulse_fit": ["収集基盤"],
        "ideastash_fit_public": ["エージェント運用"],
        "risk_notes": ["スター数だけで判断しないでください"],
        "signals": [
            {
                "source": "hn",
                "title": "Show HN: Useful repo",
                "url": "https://news.ycombinator.com/item?id=1",
            }
        ],
        "status": "candidate",
    }


def test_export_repo_radar_notes_preserves_manual_block_and_avoids_private_leaks(tmp_path: Path):
    source = tmp_path / "repo_radar.jsonl"
    source.write_text(json.dumps(_repo_row(), ensure_ascii=False) + "\n", encoding="utf-8")
    out_dir = tmp_path / "vault" / "repo-radar"
    note = out_dir / "acme__useful-repo.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        """---
repo: acme/useful-repo
adoption_status: testing
related_idea:
  - ideas/example.md
trial_result: promising
setup_cost: low
risk: medium
next_action: run smoke
---
<!-- repo-radar:auto:start -->
old generated
<!-- repo-radar:auto:end -->

<!-- repo-radar:manual:start -->
## 手動メモ

- 残したい観察
<!-- repo-radar:manual:end -->
""",
        encoding="utf-8",
    )

    stats = obsidian.export_notes(source, out_dir)

    text = note.read_text(encoding="utf-8")
    assert stats == {"written": 1, "skipped": 0}
    assert "repo: acme/useful-repo" in text
    assert "stars: 1234" in text
    assert "tags:" in text
    assert "## 概要" in text
    assert "## Codex 実装時の使いどころ" in text
    assert "[[repo-radar/acme__useful-repo]]" not in text
    assert "adoption_status: testing" in text
    assert "related_idea:\n  - ideas/example.md" in text
    assert "trial_result: promising" in text
    assert "setup_cost: low" in text
    assert "risk: medium" in text
    assert "next_action: run smoke" in text
    assert "- 残したい観察" in text
    assert "PrivateTaskName" not in text
    assert "LOCAL_IDEASTASH_PATH" not in text


def test_render_note_includes_repo_radar_operations_properties_and_valid_empty_lists():
    row = {
        **_repo_row(),
        "topics": [],
        "ideastash_fit_public": [],
        "developer_use_case": "日次レビューで候補の用途を把握できます。",
        "adoption_reason": "運用適合性: 低リスクで試用ログへ接続できるため。",
    }

    text = obsidian.render_note(row)

    assert "what_it_does: >-" in text
    assert "  日次レビューで候補の用途を把握できます。" in text
    assert "ops_fit: >-" in text
    assert "  運用適合性: 低リスクで試用ログへ接続できるため。" in text
    assert "adoption_status: candidate" in text
    assert "related_idea: []" in text
    assert "trial_result: not_tested" in text
    assert "setup_cost: unknown" in text
    assert "risk: unknown" in text
    assert "next_action: review" in text
    assert "topics: []" in text
    assert "topics:[]" not in text
    assert "ideastash_fit_public: []" in text
    assert "ideastash_fit_public:[]" not in text


def test_search_related_repos_returns_fit_reason_from_generated_notes(tmp_path: Path):
    repo_dir = tmp_path / "repo-radar"
    repo_dir.mkdir()
    (repo_dir / "acme__useful-repo.md").write_text(
        obsidian.render_note(_repo_row()),
        encoding="utf-8",
    )
    (repo_dir / "acme__visual-tool.md").write_text(
        obsidian.render_note(
            {
                **_repo_row("acme/visual-tool"),
                "topics": ["design"],
                "summary": "デザイン確認ツールです。",
                "developer_use_case": "UI の見た目確認に使えます。",
                "ideastash_fit_public": ["UI/UX 改善"],
                "score": 55,
            }
        ),
        encoding="utf-8",
    )

    results = obsidian.search_related_repos(
        repo_dir,
        query_text="MCP を使ってアイデア保存時に関連リポジトリをサジェストしたい",
        tags=["cat/automation", "area/ai"],
        max_results=1,
    )

    assert len(results) == 1
    assert results[0]["repo"] == "acme/useful-repo"
    assert results[0]["note_path"] == "repo-radar/acme__useful-repo.md"
    assert "MCP" in results[0]["fit_reason"] or "mcp" in results[0]["fit_reason"].lower()
    assert results[0]["useful_capability"] == "実装前調査に使えます。"
