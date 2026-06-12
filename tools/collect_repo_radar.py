"""Repo Radar: HN / Reddit / X で話題の GitHub リポジトリを発見し Ollama で一次評価する。

既存の Google News RSS とは別系統の観測レイヤー。GitHub リポジトリ候補と評価結果は
data/repo_radar.jsonl に分離し、IdeaStash の具体タスク名は公開データへ出さない。
"""
from __future__ import annotations

import base64
import email.utils
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import config  # noqa: E402
import llm_local  # noqa: E402

DATA = ROOT / "data"
LOG_DIR = ROOT / "_logs"


def _load_local_env() -> None:
    """AI-Pulse/.env を環境変数に反映する。既存環境変数は上書きしない。"""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_local_env()
IDEASTASH_DIR = Path(os.environ["IDEASTASH_DIR"]) if os.environ.get("IDEASTASH_DIR") else None

REPO_RADAR_PATH = DATA / "repo_radar.jsonl"
GITHUB_RE = re.compile(
    r"(?:h(?:tt|xx)ps?\s*:\s*/\s*/)?github\.com\s*/\s*([A-Za-z0-9_.-]+)\s*/\s*([A-Za-z0-9_.-]+)(?:[/?#][^\s)\]>\"']*)?",
    re.IGNORECASE,
)
EXCLUDED_REPO_NAMES = {
    "issues", "pull", "pulls", "releases", "actions", "wiki", "blob", "tree",
    "commit", "commits", "compare", "discussions", "stargazers", "forks",
}
PUBLIC_FIELDS = {
    "date", "repo", "repo_url", "name", "description", "homepage", "language",
    "license", "topics", "stars", "forks", "open_issues", "pushed_at",
    "latest_release", "signals", "score", "summary", "developer_use_case",
    "implementation_difficulty", "pricing_or_license", "ai_pulse_fit",
    "ideastash_fit_public", "risk_notes", "status",
}
REPO_RADAR_SCHEMA = {
    "type": "object",
    "required": [
        "summary",
        "developer_use_case",
        "implementation_difficulty",
        "pricing_or_license",
        "ai_pulse_fit",
        "ideastash_fit_public",
        "risk_notes",
        "score",
    ],
    "properties": {
        "summary": {"type": "string"},
        "developer_use_case": {"type": "string"},
        "implementation_difficulty": {"type": "string"},
        "pricing_or_license": {"type": "string"},
        "ai_pulse_fit": {"type": "array", "items": {"type": "string"}},
        "ideastash_fit_public": {"type": "array", "items": {"type": "string"}},
        "risk_notes": {"type": "array", "items": {"type": "string"}},
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
    },
}


def extract_github_repos(text: str) -> list[str]:
    """本文中の GitHub URL から owner/repo を重複排除して返す。"""
    repos: list[str] = []
    seen: set[str] = set()
    for match in GITHUB_RE.finditer(text or ""):
        owner = match.group(1).strip(".")
        repo = match.group(2).strip(".")
        if repo.lower().endswith(".git"):
            repo = repo[:-4].strip(".")
        if not owner or not repo:
            continue
        if repo.lower() in EXCLUDED_REPO_NAMES:
            continue
        key = f"{owner}/{repo}"
        norm = key.lower()
        if norm not in seen:
            seen.add(norm)
            repos.append(key)
    return repos


def merge_signals(items: list[dict]) -> dict[str, dict]:
    """同じ repo の Reddit/HN signal を 1 件に集約する。"""
    merged: dict[str, dict] = {}
    for item in items:
        for repo in extract_github_repos(" ".join(str(item.get(k, "")) for k in ("title", "url", "text"))):
            entry = merged.setdefault(
                repo.lower(),
                {"repo": repo, "sources": [], "score_hint": 0, "titles": [], "urls": []},
            )
            source = item.get("source") or "unknown"
            points = int(item.get("points") or 0)
            comments = int(item.get("comments") or 0)
            entry["score_hint"] += points + min(comments, 100)
            entry["sources"].append({
                "source": source,
                "title": item.get("title") or repo,
                "url": item.get("url") or "",
                "points": points,
                "comments": comments,
            })
            if item.get("title"):
                entry["titles"].append(item["title"])
            if item.get("url"):
                entry["urls"].append(item["url"])
    return merged


def _request_json(url: str, *, headers: dict[str, str] | None = None, timeout: int = 20) -> Any:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _request_text(url: str, *, headers: dict[str, str] | None = None, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "AI-Pulse-Repo-Radar/0.1",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_github_repo(repo: str, *, request_json=_request_json) -> dict:
    """GitHub API で公開 repo metadata / README / release を取得する。"""
    owner_repo = repo.strip()
    headers = _github_headers()
    base = f"https://api.github.com/repos/{owner_repo}"
    meta = request_json(base, headers=headers)
    readme = ""
    try:
        readme_payload = request_json(f"{base}/readme", headers=headers)
        if readme_payload.get("encoding") == "base64":
            readme = base64.b64decode(readme_payload.get("content", "")).decode(
                "utf-8", errors="replace"
            )
    except Exception:
        readme = ""
    latest_release = None
    try:
        release = request_json(f"{base}/releases/latest", headers=headers)
        latest_release = {
            "tag": release.get("tag_name") or "",
            "name": release.get("name") or "",
            "published_at": release.get("published_at") or "",
        }
    except Exception:
        latest_release = None
    return {
        "repo": owner_repo,
        "repo_url": meta.get("html_url") or f"https://github.com/{owner_repo}",
        "name": meta.get("name") or owner_repo.split("/")[-1],
        "description": meta.get("description") or "",
        "homepage": meta.get("homepage") or "",
        "language": meta.get("language") or "",
        "license": (meta.get("license") or {}).get("spdx_id") or "unknown",
        "topics": meta.get("topics") or [],
        "stars": int(meta.get("stargazers_count") or 0),
        "forks": int(meta.get("forks_count") or 0),
        "open_issues": int(meta.get("open_issues_count") or 0),
        "pushed_at": meta.get("pushed_at") or "",
        "latest_release": latest_release,
        "readme_excerpt": readme[:4000],
    }


def fetch_hn_candidates(*, request_json=_request_json, limit: int = 60) -> list[dict]:
    """HN 公式 API から GitHub repo URL を含む候補を収集する。"""
    bases = [
        "https://hacker-news.firebaseio.com/v0/topstories.json",
        "https://hacker-news.firebaseio.com/v0/beststories.json",
        "https://hacker-news.firebaseio.com/v0/showstories.json",
        "https://hacker-news.firebaseio.com/v0/newstories.json",
    ]
    ids: list[int] = []
    seen: set[int] = set()
    for url in bases:
        try:
            for item_id in request_json(url)[: max(10, limit // len(bases))]:
                if item_id not in seen:
                    seen.add(item_id)
                    ids.append(item_id)
        except Exception:
            continue
    items: list[dict] = []
    for item_id in ids[:limit]:
        try:
            item = request_json(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json")
        except Exception:
            continue
        text = " ".join(str(item.get(k, "")) for k in ("title", "url", "text"))
        if "github.com/" not in text.lower():
            continue
        items.append({
            "source": "hn",
            "title": item.get("title") or "",
            "url": item.get("url") or f"https://news.ycombinator.com/item?id={item_id}",
            "text": item.get("text") or "",
            "points": item.get("score") or 0,
            "comments": item.get("descendants") or 0,
        })
    return items


def fetch_reddit_candidates(
    *,
    request_json=_request_json,
    limit: int = 40,
    token: str | None = None,
) -> tuple[list[dict], bool]:
    """Reddit OAuth API から GitHub repo URL を含む候補を収集する。

    bearer token または client_credentials 設定が無い場合は Reddit だけ degraded として skip する。
    """
    ua = os.environ.get("REDDIT_USER_AGENT")
    if not ua:
        return [], True
    bearer = token or os.environ.get("REDDIT_BEARER_TOKEN") or _fetch_reddit_token(ua)
    if not bearer:
        return [], True
    headers = {"Authorization": f"Bearer {bearer}", "User-Agent": ua}
    subreddits = os.environ.get(
        "REPO_RADAR_SUBREDDITS",
        "LocalLLaMA,ClaudeAI,ClaudeCode,OpenAI,MachineLearning,programming,selfhosted",
    )
    items: list[dict] = []
    for sub in [s.strip() for s in subreddits.split(",") if s.strip()]:
        url = (
            f"https://oauth.reddit.com/r/{urllib.parse.quote(sub)}/search"
            f"?q=site%3Agithub.com&restrict_sr=1&sort=top&t=week&limit={limit}"
        )
        try:
            payload = request_json(url, headers=headers)
        except Exception:
            continue
        for child in (payload.get("data") or {}).get("children") or []:
            data = child.get("data") or {}
            text = " ".join(str(data.get(k, "")) for k in ("title", "url", "selftext"))
            if "github.com/" not in text.lower():
                continue
            items.append({
                "source": f"reddit:{sub}",
                "title": data.get("title") or "",
                "url": data.get("url") or "",
                "text": data.get("selftext") or "",
                "points": data.get("score") or 0,
                "comments": data.get("num_comments") or 0,
            })
    return items, False


def fetch_x_candidates(
    *,
    request_json=_request_json,
    limit: int = 40,
    token: str | None = None,
) -> tuple[list[dict], bool]:
    """X recent search から GitHub repo URL を含む候補を収集する。

    REPO_RADAR_ENABLE_X=1 かつ X_BEARER_TOKEN がある場合だけ実行する。
    明示有効化されていない場合は、課金防止のため X 公式 API source だけ skip する。
    """
    if os.environ.get("REPO_RADAR_ENABLE_X") != "1":
        return [], False
    bearer = token or os.environ.get("X_BEARER_TOKEN")
    if not bearer:
        return [], True
    raw_queries = os.environ.get(
        "REPO_RADAR_X_QUERIES",
        "github.com (AI OR agent OR agents OR LLM OR MCP OR Claude OR Codex OR Cursor OR RAG) -is:retweet lang:en",
    )
    headers = {
        "Authorization": f"Bearer {bearer}",
        "User-Agent": "AI-Pulse-Repo-Radar/0.1",
    }
    items: list[dict] = []
    per_query_limit = max(10, min(100, limit))
    for query in [q.strip() for q in raw_queries.splitlines() if q.strip()]:
        params = urllib.parse.urlencode({
            "query": query,
            "max_results": str(per_query_limit),
            "tweet.fields": "created_at,public_metrics",
        })
        url = f"https://api.x.com/2/tweets/search/recent?{params}"
        try:
            payload = request_json(url, headers=headers)
        except Exception:
            continue
        for post in payload.get("data") or []:
            text = post.get("text") or ""
            if "github.com/" not in text.lower():
                continue
            metrics = post.get("public_metrics") or {}
            post_id = str(post.get("id") or "")
            author_url = f"https://x.com/i/web/status/{post_id}" if post_id else ""
            items.append({
                "source": "x",
                "title": text[:180],
                "url": author_url,
                "text": text,
                "points": (
                    int(metrics.get("like_count") or 0)
                    + int(metrics.get("retweet_count") or 0) * 2
                    + int(metrics.get("quote_count") or 0) * 2
                ),
                "comments": int(metrics.get("reply_count") or 0),
            })
    return items[:limit], False


def fetch_x_rss_candidates(
    *,
    rss_paths: str | None = None,
    request_text=_request_text,
    limit: int = 80,
) -> tuple[list[dict], bool]:
    """book000/twitter-rss が生成した RSS XML から GitHub repo 候補を収集する。

    REPO_RADAR_X_RSS_PATHS は改行またはセミコロン区切りで、RSS XML ファイル、RSS XML を含む
    ディレクトリ、または URL を指定できる。未設定なら X RSS source は単に skip する。
    """
    raw_paths = rss_paths if rss_paths is not None else os.environ.get("REPO_RADAR_X_RSS_PATHS", "")
    locations = _split_rss_locations(raw_paths)
    if not locations:
        return [], False
    items: list[dict] = []
    degraded = False
    for location in locations:
        try:
            for name, xml_text in _iter_rss_xml(location, request_text=request_text):
                items.extend(_parse_x_rss_items(xml_text, source_name=f"x-rss:{name}"))
        except Exception:
            degraded = True
            continue
    return items[:limit], degraded


def _split_rss_locations(raw_paths: str) -> list[str]:
    return [part.strip() for part in re.split(r"[\r\n;]+", raw_paths or "") if part.strip()]


def _iter_rss_xml(location: str, *, request_text=_request_text) -> list[tuple[str, str]]:
    if location.startswith(("http://", "https://")):
        return [(urllib.parse.urlparse(location).path.rsplit("/", 1)[-1] or "remote", request_text(location))]
    path = Path(location).expanduser()
    if path.is_dir():
        return [(p.stem, p.read_text(encoding="utf-8", errors="replace")) for p in sorted(path.glob("*.xml"))]
    return [(path.stem, path.read_text(encoding="utf-8", errors="replace"))]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _parse_x_rss_items(xml_text: str, *, source_name: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    rows: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=10)
    for item in root.iter():
        if _local_name(item.tag) != "item":
            continue
        fields = {_local_name(child.tag): (child.text or "") for child in list(item)}
        published = _parse_rss_datetime(fields.get("pubdate") or fields.get("title") or "")
        if published and published < cutoff:
            continue
        text = " ".join(
            fields.get(key, "") for key in ("title", "link", "description", "encoded", "guid")
        ).strip()
        if "github.com/" not in text.lower():
            continue
        rows.append({
            "source": source_name,
            "title": fields.get("title") or text[:180],
            "url": fields.get("link") or fields.get("guid") or "",
            "text": fields.get("description") or fields.get("encoded") or text,
            "points": 0,
            "comments": 0,
        })
    return rows


def _parse_rss_datetime(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(
                tzinfo=timezone(timedelta(hours=9))
            ).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _fetch_reddit_token(user_agent: str) -> str | None:
    """REDDIT_CLIENT_ID / SECRET から app-only OAuth token を取得する。"""
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("ascii")
    req = urllib.request.Request(
        "https://www.reddit.com/api/v1/access_token",
        data=data,
        headers={
            "Authorization": f"Basic {auth}",
            "User-Agent": user_agent,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.load(resp)
    except Exception:
        return None
    token = payload.get("access_token")
    return str(token) if token else None


def _read_ideastash_tasks(ideas_dir: Path | None = None) -> list[dict]:
    if ideas_dir is not None:
        root = ideas_dir
    elif IDEASTASH_DIR is not None:
        root = IDEASTASH_DIR / "ideas"
    else:
        return []
    if not root.exists():
        return []
    tasks: list[dict] = []
    for path in sorted(root.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        fm = _frontmatter(text)
        status = str(fm.get("status") or "stash")
        if status in {"done", "dropped"}:
            continue
        title = str(fm.get("title") or path.stem)
        tags = fm.get("tags") if isinstance(fm.get("tags"), list) else []
        outline = fm.get("implementation_outline") if isinstance(fm.get("implementation_outline"), list) else []
        tasks.append({
            "title": title,
            "file": path.name,
            "status": status,
            "score": int(fm.get("score") or 0),
            "tags": tags,
            "implementation_outline": outline,
            "public_category": _public_task_category(title, tags, outline),
        })
    return sorted(tasks, key=lambda x: x["score"], reverse=True)


def _frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    lines = parts[1].splitlines()
    result: dict[str, Any] = {}
    current_key: str | None = None
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            current_key = key
            if value:
                result[key] = value.strip('"')
            else:
                result[key] = []
            continue
        if current_key and line.lstrip().startswith("-"):
            item = line.lstrip()[1:].strip().strip('"')
            if not isinstance(result.get(current_key), list):
                result[current_key] = []
            result[current_key].append(item)
    return result


def _public_task_category(title: str, tags: list[str], outline: list[str]) -> str:
    text = " ".join([title, *tags, *outline]).lower()
    rules = [
        ("ニュース収集・配信", ("news", "rss", "配信", "通知", "digest")),
        ("UI/UX 改善", ("ui", "ux", "dashboard", "画面", "見栄え", "artifact")),
        ("エージェント運用", ("agent", "mcp", "claude", "codex", "自動")),
        ("文書・仕様生成", ("doc", "html", "spec", "ppt", "仕様", "スライド")),
        ("データ基盤", ("db", "csv", "sqlite", "kb", "knowledge", "データ")),
    ]
    for label, needles in rules:
        if any(n in text for n in needles):
            return label
    return "未分類の実装候補"


def _validate_eval(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise llm_local.LLMError("Repo Radar 評価が object ではありません")
    required = REPO_RADAR_SCHEMA["required"]
    missing = [key for key in required if key not in payload]
    if missing:
        raise llm_local.LLMError(f"Repo Radar 評価の必須キー欠落: {missing}")
    if not isinstance(payload["score"], int) or not 0 <= payload["score"] <= 100:
        raise llm_local.LLMError("Repo Radar 評価 score が 0〜100 の int ではありません")
    for key in ("summary", "developer_use_case", "implementation_difficulty", "pricing_or_license"):
        if not isinstance(payload[key], str) or not payload[key].strip():
            raise llm_local.LLMError(f"Repo Radar 評価 {key} が空です")
    for key in ("ai_pulse_fit", "ideastash_fit_public", "risk_notes"):
        if not isinstance(payload[key], list) or not all(isinstance(v, str) and v.strip() for v in payload[key]):
            raise llm_local.LLMError(f"Repo Radar 評価 {key} が文字列配列ではありません")
    return payload


def _ollama_chat_json(
    repo: dict,
    signal: dict,
    idea_tasks: list[dict],
    *,
    call_once: Any | None = None,
) -> dict:
    public_tasks = [
        {
            "category": task["public_category"],
            "status": task["status"],
            "score": task["score"],
            "tags": task["tags"][:5],
        }
        for task in idea_tasks[:12]
    ]
    prompt = (
        "あなたは AI-Pulse の Repo Radar 評価者です。AI 駆動開発に役立つ GitHub "
        "リポジトリかを一次評価してください。公開ページに出すため、個人タスク名、"
        "ローカルパス、ファイル名は絶対に出力しないでください。\n\n"
        f"[repo]\n{json.dumps({k: v for k, v in repo.items() if k != 'readme_excerpt'}, ensure_ascii=False)}\n\n"
        f"[readme excerpt]\n{repo.get('readme_excerpt', '')[:3000]}\n\n"
        f"[community signal]\n{json.dumps(signal, ensure_ascii=False)}\n\n"
        f"[匿名化済み IdeaStash カテゴリ]\n{json.dumps(public_tasks, ensure_ascii=False)}\n\n"
        "[出力]\n"
        "- summary: 何をする repo かを日本語 2 文以内。\n"
        "- developer_use_case: AI 駆動開発でどう使えるか。\n"
        "- implementation_difficulty: easy|medium|hard と理由。\n"
        "- pricing_or_license: OSS / 商用 / 課金不明 / API key 必要など。\n"
        "- ai_pulse_fit: AI-Pulse のどの機能に効くかを匿名カテゴリで列挙。\n"
        "- ideastash_fit_public: 具体タスク名ではなく匿名カテゴリだけを列挙。\n"
        "- risk_notes: ライセンス、保守、セキュリティ、課金の懸念。\n"
        "- score: 0〜100 の整数。実装効用を最重視。\n"
        "純粋な JSON だけを返してください。"
    )
    last_err: Exception | None = None
    for attempt in range(config.OLLAMA_MAX_RETRIES + 1):
        try:
            if call_once is not None:
                payload = call_once(prompt, REPO_RADAR_SCHEMA)
            else:
                payload = _call_ollama(prompt)
            return _validate_eval(payload)
        except Exception as exc:
            last_err = exc
            if attempt < config.OLLAMA_MAX_RETRIES:
                time.sleep(2.0)
    raise llm_local.LLMError(f"Repo Radar Ollama 評価失敗: {last_err}")


def _call_ollama(prompt: str) -> dict:
    req = {
        "model": config.OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "think": False,
        "format": REPO_RADAR_SCHEMA,
        "stream": False,
        "options": {"temperature": config.OLLAMA_TEMPERATURE},
    }
    data = json.dumps(req).encode("utf-8")
    url = f"{config.OLLAMA_HOST}/api/chat"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}),
            timeout=config.OLLAMA_TIMEOUT_SEC,
        ) as resp:
            payload = json.load(resp)
    except urllib.error.URLError as exc:
        raise llm_local.LLMError(f"Ollama 接続失敗（{url}）: {exc}") from exc
    raw = (payload.get("message") or {}).get("content") or ""
    if not raw.strip():
        raise llm_local.LLMError("Ollama が空応答です")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise llm_local.LLMError(f"Ollama JSON パース失敗: {exc}") from exc


def _private_matches(repo: dict, evaluation: dict, tasks: list[dict]) -> list[dict]:
    categories = set(evaluation.get("ideastash_fit_public") or [])
    if not categories:
        return []
    rows = []
    for task in tasks[:20]:
        if task["public_category"] in categories:
            rows.append({
                "repo": repo["repo"],
                "idea_file": task["file"],
                "idea_title": task["title"],
                "public_category": task["public_category"],
                "reason": f"評価カテゴリ {task['public_category']} と一致",
            })
    return rows


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _write_public_rows(path: Path, new_rows: list[dict]) -> None:
    existing = _load_existing(path)
    by_key = {(row.get("date"), str(row.get("repo", "")).lower()): row for row in existing}
    for row in new_rows:
        by_key[(row.get("date"), str(row.get("repo", "")).lower())] = {
            key: value for key, value in row.items() if key in PUBLIC_FIELDS
        }
    rows = sorted(by_key.values(), key=lambda r: (r.get("date", ""), r.get("score", 0)), reverse=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows[:200]:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def collect(
    *,
    max_candidates: int = 20,
    max_enrich: int = 12,
    max_evaluate: int = 8,
    today: str | None = None,
    request_json=_request_json,
    eval_call_once: Any | None = None,
    output_path: Path = REPO_RADAR_PATH,
    log_dir: Path = LOG_DIR,
    ideas_dir: Path | None = None,
) -> dict:
    """Repo Radar を 1 回実行し、公開 JSONL と非公開 match log を更新する。"""
    date_key = today or datetime.now(timezone.utc).date().isoformat()
    stats = {
        "candidates": 0,
        "enriched": 0,
        "evaluated": 0,
        "skipped": 0,
        "degraded": 0,
        "ollama_errors": 0,
        "output_path": str(output_path),
    }
    hn_items = fetch_hn_candidates(request_json=request_json)
    x_rss_items, x_rss_degraded = fetch_x_rss_candidates()
    if x_rss_degraded:
        stats["degraded"] += 1
    x_items, x_degraded = fetch_x_candidates(request_json=request_json)
    if x_degraded:
        stats["degraded"] += 1
    reddit_items, reddit_degraded = fetch_reddit_candidates(request_json=request_json)
    if reddit_degraded:
        stats["degraded"] += 1
    merged = merge_signals([*hn_items, *x_rss_items, *x_items, *reddit_items])
    signals = sorted(merged.values(), key=lambda item: item["score_hint"], reverse=True)[:max_candidates]
    stats["candidates"] = len(signals)
    idea_tasks = _read_ideastash_tasks(ideas_dir)
    public_rows: list[dict] = []
    private_rows: list[dict] = []
    source_counts = Counter()
    for signal in signals[:max_enrich]:
        repo_key = signal["repo"]
        try:
            repo = fetch_github_repo(repo_key, request_json=request_json)
            stats["enriched"] += 1
        except Exception:
            stats["skipped"] += 1
            continue
        if len(public_rows) >= max_evaluate:
            continue
        try:
            evaluation = _ollama_chat_json(repo, signal, idea_tasks, call_once=eval_call_once)
        except Exception:
            stats["ollama_errors"] += 1
            stats["degraded"] += 1
            continue
        for s in signal.get("sources") or []:
            source_counts[s.get("source", "unknown")] += 1
        row = {
            **{key: value for key, value in repo.items() if key != "readme_excerpt"},
            **evaluation,
            "date": date_key,
            "signals": signal.get("sources") or [],
            "status": "evaluated",
        }
        public_rows.append(row)
        private_rows.extend(_private_matches(repo, evaluation, idea_tasks))
        stats["evaluated"] += 1
    _write_public_rows(output_path, public_rows)
    log_path = log_dir / f"repo_radar_matches_{date_key.replace('-', '')}.jsonl"
    _append_jsonl(log_path, private_rows)
    stats["private_match_path"] = str(log_path) if private_rows else None
    stats["source_counts"] = dict(source_counts)
    return stats


def load_public_rows(path: Path = REPO_RADAR_PATH, *, limit: int = 80) -> list[dict]:
    """SSG 用に公開 repo radar rows を新しい順で読む。"""
    rows = _load_existing(path)
    rows.sort(key=lambda r: (r.get("date", ""), r.get("score", 0), r.get("stars", 0)), reverse=True)
    return rows[:limit]


def main() -> None:
    stats = collect()
    print(
        "[repo_radar] "
        f"candidates={stats['candidates']} enriched={stats['enriched']} "
        f"evaluated={stats['evaluated']} skipped={stats['skipped']} "
        f"degraded={stats['degraded']} ollama_errors={stats['ollama_errors']}"
    )


if __name__ == "__main__":
    main()
