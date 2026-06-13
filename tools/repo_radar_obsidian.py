"""Repo Radar の公開 JSONL を IdeaStash 用 Obsidian ノートへ展開する。"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

AUTO_START = "<!-- repo-radar:auto:start -->"
AUTO_END = "<!-- repo-radar:auto:end -->"
MANUAL_START = "<!-- repo-radar:manual:start -->"
MANUAL_END = "<!-- repo-radar:manual:end -->"
DEFAULT_VAULT = Path(os.environ.get("IDEASTASH_VAULT", Path.home() / "Obsidian" / "IdeaStash"))


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return '""'
    text = str(value)
    if not text:
        return '""'
    if re.search(r"[:#\[\]{},&*!|>'\"%@`?]|\s$", text) or text[0].isspace():
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def _yaml_list(values: list[Any]) -> list[str]:
    if not values:
        return ["[]"]
    return [""] + [f"  - {_yaml_scalar(v)}" for v in values]


def _safe_filename(repo: str) -> str:
    owner, name = repo.split("/", 1)
    return f"{owner}__{name}.md"


def _frontmatter(row: dict[str, Any]) -> str:
    tags = sorted({
        "repo-radar",
        "cat/repository",
        *[f"topic/{t}" for t in row.get("topics") or []],
        *[f"fit/{t}" for t in row.get("ideastash_fit_public") or []],
    })
    fields: list[tuple[str, Any]] = [
        ("repo", row.get("repo", "")),
        ("repo_url", row.get("repo_url", "")),
        ("status", row.get("status") or "candidate"),
        ("score", row.get("score", 0)),
        ("stars", row.get("stars", 0)),
        ("language", row.get("language", "")),
        ("license", row.get("license", "")),
        ("created_at", row.get("created_at", "")),
        ("pushed_at", row.get("pushed_at", "")),
        ("date", row.get("date", "")),
    ]
    lines = ["---"]
    for key, value in fields:
        lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("topics:" + "\n".join(_yaml_list(row.get("topics") or [])))
    lines.append("ai_pulse_fit:" + "\n".join(_yaml_list(row.get("ai_pulse_fit") or [])))
    lines.append("ideastash_fit_public:" + "\n".join(_yaml_list(row.get("ideastash_fit_public") or [])))
    lines.append("tags:" + "\n".join(_yaml_list(tags)))
    lines.append("---")
    return "\n".join(lines)


def _bullets(items: list[Any]) -> list[str]:
    values = [str(v).strip() for v in items if str(v).strip()]
    return [f"- {v}" for v in values] if values else ["- なし"]


def _feature_lines(row: dict[str, Any]) -> list[str]:
    features = row.get("feature_outline") or []
    lines: list[str] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        lens = str(feature.get("lens") or "Feature").strip()
        text = str(feature.get("text") or "").strip()
        if text:
            lines.append(f"- **{lens}**: {text}")
    return lines or ["- なし"]


def _signal_lines(row: dict[str, Any]) -> list[str]:
    lines = []
    for signal in row.get("signals") or []:
        if not isinstance(signal, dict):
            continue
        title = str(signal.get("title") or signal.get("source") or "source").strip()
        url = str(signal.get("url") or "").strip()
        source = str(signal.get("source") or "").strip()
        if url:
            lines.append(f"- [{title}]({url}) ({source})")
        elif title:
            lines.append(f"- {title} ({source})")
    return lines or ["- なし"]


def _auto_body(row: dict[str, Any]) -> str:
    repo = str(row.get("repo") or "").strip()
    repo_url = str(row.get("repo_url") or f"https://github.com/{repo}").strip()
    lines = [
        AUTO_START,
        "",
        f"# {repo}",
        "",
        "## 概要",
        "",
        str(row.get("summary") or row.get("description") or "").strip() or "概要未設定",
        "",
        "## 採用レンズ",
        "",
        *_feature_lines(row),
        "",
        "## 使える機能",
        "",
        str(row.get("developer_use_case") or "").strip() or "未設定",
        "",
        "## 採用理由",
        "",
        str(row.get("adoption_reason") or "").strip() or "未設定",
        "",
        "## 注意点",
        "",
        *_bullets(row.get("risk_notes") or []),
        "",
        "## Codex 実装時の使いどころ",
        "",
        f"- {str(row.get('developer_use_case') or '実装前の採用検討に使えます。').strip()}",
        f"- 難易度: {str(row.get('implementation_difficulty') or '未設定').strip()}",
        f"- ライセンス/課金: {str(row.get('pricing_or_license') or row.get('license') or '未設定').strip()}",
        "",
        "## 関連リンク",
        "",
        f"- GitHub: {repo_url}",
        *_signal_lines(row),
        "",
        AUTO_END,
    ]
    return "\n".join(lines).rstrip() + "\n"


def _manual_block(existing: str | None) -> str:
    if existing and MANUAL_START in existing and MANUAL_END in existing:
        start = existing.index(MANUAL_START)
        end = existing.index(MANUAL_END) + len(MANUAL_END)
        return existing[start:end].strip()
    return "\n".join([
        MANUAL_START,
        "## 手動メモ",
        "",
        "- ",
        MANUAL_END,
    ])


def render_note(row: dict[str, Any], existing: str | None = None) -> str:
    """1 repo の Obsidian ノート本文を生成する。"""
    return "\n\n".join([
        _frontmatter(row),
        _auto_body(row).strip(),
        _manual_block(existing),
    ]) + "\n"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def export_notes(source_path: Path, output_dir: Path) -> dict[str, int]:
    """公開 Repo Radar JSONL から Obsidian ノートを生成する。"""
    rows = _load_jsonl(source_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    for row in rows:
        repo = str(row.get("repo") or "").strip()
        if "/" not in repo:
            skipped += 1
            continue
        target = output_dir / _safe_filename(repo)
        existing = target.read_text(encoding="utf-8") if target.exists() else None
        text = render_note(row, existing)
        if existing == text:
            skipped += 1
            continue
        target.write_text(text, encoding="utf-8")
        written += 1
    return {"written": written, "skipped": skipped}


def _parse_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    data: dict[str, Any] = {}
    current: str | None = None
    for raw in parts[1].splitlines():
        if not raw.strip():
            continue
        if not raw.startswith(" ") and ":" in raw:
            key, value = raw.split(":", 1)
            current = key.strip()
            value = value.strip()
            data[current] = value.strip('"') if value else []
            continue
        if current and raw.lstrip().startswith("-"):
            if not isinstance(data.get(current), list):
                data[current] = []
            data[current].append(raw.lstrip()[1:].strip().strip('"'))
    return data


def _tokens(*values: Any) -> set[str]:
    text = " ".join(
        " ".join(v) if isinstance(v, list) else str(v)
        for v in values
        if v is not None
    ).lower()
    return {
        token
        for token in re.findall(r"[a-z0-9_./+-]{2,}|[ぁ-んァ-ン一-龥]{2,}", text)
        if token not in {"https", "github", "repo", "radar"}
    }


def _section_text(text: str, heading: str) -> str:
    pattern = re.compile(rf"^## {re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return ""
    rest = text[match.end():]
    next_heading = re.search(r"^## ", rest, re.MULTILINE)
    return rest[: next_heading.start()].strip() if next_heading else rest.strip()


def search_related_repos(
    notes_dir: Path,
    *,
    query_text: str,
    tags: list[str] | None = None,
    max_results: int = 3,
) -> list[dict[str, Any]]:
    """Obsidian Repo Radar ノートからタスクに近い repo 候補を返す。"""
    query_tokens = _tokens(query_text, tags or [])
    results: list[dict[str, Any]] = []
    for path in sorted(notes_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        repo = str(fm.get("repo") or path.stem.replace("__", "/"))
        haystack_tokens = _tokens(
            repo,
            fm.get("topics") or [],
            fm.get("tags") or [],
            fm.get("ideastash_fit_public") or [],
            _section_text(text, "概要"),
            _section_text(text, "使える機能"),
        )
        overlap = sorted(query_tokens & haystack_tokens)
        score = len(overlap) * 10 + int(fm.get("score") or 0) / 100
        if score <= 0:
            continue
        useful = _section_text(text, "使える機能").splitlines()
        risk = _section_text(text, "注意点").splitlines()
        results.append({
            "repo": repo,
            "note_path": f"repo-radar/{path.name}",
            "fit_reason": "一致した観点: " + ", ".join(overlap[:5]),
            "useful_capability": useful[0].lstrip("- ").strip() if useful else "",
            "risk_note": risk[0].lstrip("- ").strip() if risk else "",
            "score": int(fm.get("score") or 0),
            "_rank": score,
        })
    results.sort(key=lambda item: (item["_rank"], item["score"]), reverse=True)
    return [{k: v for k, v in item.items() if k != "_rank"} for item in results[:max_results]]


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    export_parser = sub.add_parser("export")
    export_parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "repo_radar.jsonl")
    export_parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    search_parser = sub.add_parser("search")
    search_parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--tag", action="append", default=[])
    search_parser.add_argument("--max-results", type=int, default=3)
    args = parser.parse_args()
    if args.command in (None, "export"):
        stats = export_notes(args.source, args.vault / "repo-radar")
        print(f"[repo_radar_obsidian] written={stats['written']} skipped={stats['skipped']}")
        return
    results = search_related_repos(
        args.vault / "repo-radar",
        query_text=args.query,
        tags=args.tag,
        max_results=args.max_results,
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
