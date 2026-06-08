#!/usr/bin/env python3
"""entity.logo を公式ページ由来の画像で backfill する。

PPT 生成時に Web 検索へ戻らないよう、AI-Pulse 本体側でロゴ候補を取得・検証し、
repo 内の assets/service-icons/<entity_id>.png に正規化して保存する。
"""
from __future__ import annotations

import argparse
import html.parser
import json
import mimetypes
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ENTITIES = DATA / "entities.jsonl"
ICON_DIR = ROOT / "assets" / "service-icons"
UA = "AI-Pulse-logo-backfill/1.0"
LICENSE_NOTE = "official site asset, redistribution not verified"
BRAND_PATHS = ("brand", "branding", "press", "media", "media-kit", "logos")
ICON_RELS = {"icon", "shortcut icon", "apple-touch-icon", "apple-touch-icon-precomposed"}
ENTITY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
THIRD_PARTY_HOSTS = {
    "arxiv.org",
    "github.com",
    "huggingface.co",
    "techtimes.com",
    "electrek.co",
    "youtube.com",
    "globenewswire.com",
    "marketsandmarkets.com",
    "mordorintelligence.com",
    "marknteladvisors.com",
}


@dataclass(frozen=True)
class Candidate:
    url: str
    source_page: str
    kind: str


class LinkParser(html.parser.HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: list[Candidate] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() == "link":
            rel = " ".join(attr.get("rel", "").lower().split())
            href = attr.get("href", "").strip()
            if not href:
                return
            url = urllib.parse.urljoin(self.base_url, href)
            if rel in ICON_RELS or any(part in ICON_RELS for part in rel.split()):
                self.links.append(Candidate(url=url, source_page=self.base_url, kind=rel or "icon"))
        if tag.lower() == "meta":
            key = (attr.get("property") or attr.get("name") or "").lower()
            content = attr.get("content", "").strip()
            if key in {"og:image", "twitter:image"} and content:
                self.links.append(Candidate(
                    url=urllib.parse.urljoin(self.base_url, content),
                    source_page=self.base_url,
                    kind=key,
                ))


def load_entities(path: Path = ENTITIES) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_entities(entities: Iterable[dict], path: Path = ENTITIES) -> None:
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for entity in entities:
            f.write(json.dumps(entity, ensure_ascii=False) + "\n")
    tmp.replace(path)


def fetch(url: str, *, timeout: int = 15) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read(5_000_000)
        ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        return data, ctype


def host_of(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def is_third_party_url(url: str) -> bool:
    host = host_of(url)
    return host in THIRD_PARTY_HOSTS or any(host.endswith(f".{h}") for h in THIRD_PARTY_HOSTS)


def is_official_source(entity: dict, source: str) -> bool:
    if "/" in source:
        return False
    source_l = source.lower()
    keys = [entity.get("vendor", ""), entity.get("name", "")]
    return any(key and key.lower() in source_l for key in keys)


def official_pages(entity: dict) -> list[str]:
    pages: list[str] = []
    logo = entity.get("logo") or {}
    if (
        isinstance(logo, dict)
        and isinstance(logo.get("source_page"), str)
        and not is_third_party_url(logo["source_page"])
    ):
        pages.append(logo["source_page"])
    for item in entity.get("history") or []:
        source = str(item.get("source") or "")
        url = item.get("url")
        if (
            isinstance(url, str)
            and url.startswith(("http://", "https://"))
            and is_official_source(entity, source)
            and not is_third_party_url(url)
        ):
            pages.append(url)
    home_pages: list[str] = []
    for page in pages:
        parsed = urllib.parse.urlparse(page)
        if parsed.scheme and parsed.netloc:
            home = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/", "", "", ""))
            home_pages.append(home)
            for suffix in BRAND_PATHS:
                home_pages.append(urllib.parse.urljoin(home, suffix))
    out: list[str] = []
    for page in [*home_pages, *pages]:
        if page not in out:
            out.append(page)
    return out


def discover_candidates(entity: dict, *, limit_pages: int = 8) -> list[Candidate]:
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for page in official_pages(entity)[:limit_pages]:
        try:
            data, ctype = fetch(page)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"  page_skip {page} ({type(exc).__name__}: {exc})")
            continue
        if ctype.startswith("image/"):
            cand = Candidate(url=page, source_page=page, kind="direct-image")
            if cand.url not in seen:
                candidates.append(cand)
                seen.add(cand.url)
            continue
        if "html" not in ctype and ctype:
            continue
        parser = LinkParser(page)
        try:
            parser.feed(data.decode("utf-8", errors="replace"))
        except Exception as exc:
            print(f"  html_parse_skip {page} ({type(exc).__name__}: {exc})")
            continue
        for cand in parser.links:
            if cand.url not in seen:
                candidates.append(cand)
                seen.add(cand.url)
    return sorted(candidates, key=candidate_rank)


def candidate_rank(cand: Candidate) -> tuple[int, str]:
    kind = cand.kind.lower()
    url_l = cand.url.lower()
    if kind in {"og:image", "twitter:image"}:
        return (3, cand.url)
    if "logo" in url_l or "brand" in url_l:
        return (0, cand.url)
    if "apple-touch-icon" in kind:
        return (1, cand.url)
    if "icon" in kind or "favicon" in url_l:
        return (2, cand.url)
    return (4, cand.url)


def normalize_logo(data: bytes, dest: Path) -> tuple[int, int, str]:
    try:
        from PIL import Image
    except ModuleNotFoundError as exc:
        raise RuntimeError("Pillow が必要です。`pip install -e .` を実行してください。") from exc

    with Image.open(BytesIO(data)) as img:
        img.load()
        img = img.convert("RGBA")
        src_w, src_h = img.size
        side = max(src_w, src_h)
        canvas = Image.new("RGBA", (side, side), (255, 255, 255, 0))
        canvas.alpha_composite(img, ((side - src_w) // 2, (side - src_h) // 2))
        if side > 512:
            canvas = canvas.resize((512, 512), Image.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(dest, format="PNG")
    with Image.open(dest) as verify:
        verify.verify()
    return src_w, src_h, "image/png"


def status_for(cand: Candidate, width: int, height: int) -> str:
    kind = cand.kind.lower()
    if kind in {"og:image", "twitter:image"}:
        return "candidate"
    if "icon" in kind or "favicon" in cand.url.lower():
        return "candidate"
    if min(width, height) < 96:
        return "candidate"
    return "verified"


def logo_record(entity_id: str, cand: Candidate, status: str) -> dict:
    return {
        "path": f"assets/service-icons/{entity_id}.png",
        "source_url": cand.url,
        "source_page": cand.source_page,
        "fetched_at": date.today().isoformat(),
        "license_note": LICENSE_NOTE,
        "status": status,
    }


def icon_path_for(entity_id: str) -> Path:
    if not ENTITY_ID_RE.match(entity_id):
        raise ValueError(f"unsafe entity_id for icon path: {entity_id!r}")
    return ICON_DIR / f"{entity_id}.png"


def missing_record() -> dict:
    return {
        "fetched_at": date.today().isoformat(),
        "license_note": "official logo source not found",
        "status": "missing",
    }


def process_entity(entity: dict, *, dry_run: bool) -> bool:
    eid = entity["entity_id"]
    print(f"\n[{eid}] {entity['name']}")
    candidates = discover_candidates(entity)
    print(f"  candidates={len(candidates)}")
    for cand in candidates[:8]:
        print(f"  candidate kind={cand.kind} url={cand.url} page={cand.source_page}")
    if dry_run:
        return False
    dest = icon_path_for(eid)
    for cand in candidates:
        try:
            data, ctype = fetch(cand.url)
            if ctype and not ctype.startswith("image/"):
                guessed = mimetypes.guess_type(urllib.parse.urlparse(cand.url).path)[0] or ""
                if not guessed.startswith("image/"):
                    print(f"  skip_non_image mime={ctype} url={cand.url}")
                    continue
            width, height, mime = normalize_logo(data, dest)
            status = status_for(cand, width, height)
            entity["logo"] = logo_record(eid, cand, status)
            print(
                f"  saved path={entity['logo']['path']} mime={mime} "
                f"source_mime={ctype or 'unknown'} size={width}x{height} status={status}"
            )
            return True
        except Exception as exc:
            print(f"  image_skip {cand.url} ({type(exc).__name__}: {exc})")
    entity["logo"] = missing_record()
    if dest.exists():
        dest.unlink()
        print(f"  removed stale path=assets/service-icons/{eid}.png")
    print("  missing official logo source")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="候補探索だけを行い、画像と jsonl を書かない")
    ap.add_argument("--limit", type=int, default=0, help="先頭 N entity だけ処理する")
    ap.add_argument("--entity", action="append", default=[], help="entity_id を指定して処理する（複数可）")
    ap.add_argument("--force", action="store_true", help="既存 logo を再取得する")
    args = ap.parse_args()

    entities = load_entities()
    targets = entities
    if args.entity:
        ids = set(args.entity)
        targets = [e for e in entities if e["entity_id"] in ids]
        missing = ids - {e["entity_id"] for e in targets}
        if missing:
            print(f"unknown entity: {', '.join(sorted(missing))}", file=sys.stderr)
            return 2
    if args.limit:
        targets = targets[: args.limit]

    changed = 0
    for entity in targets:
        logo = entity.get("logo") or {}
        if logo and not args.force:
            print(f"\n[{entity['entity_id']}] skip existing logo status={logo.get('status')}")
            continue
        if process_entity(entity, dry_run=args.dry_run):
            changed += 1
        time.sleep(0.2)

    if not args.dry_run and changed:
        write_entities(entities)
        print(f"\nupdated entities={changed} file={ENTITIES}")
    else:
        print(f"\nupdated entities=0 dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
