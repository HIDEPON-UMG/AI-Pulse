#!/usr/bin/env python3
"""URL 偽造防止: entities.jsonl / events.jsonl の全 URL を実機で生存検証する境界モジュール。

# なぜこれが必要か (News-Grasp 2026-06-03 三菱UFJ FX_Monthly 事故の横展開)

LLM (Claude セッション) は記憶ベースで URL を捏造する既知バグがある。News-Grasp で
全 803 件中 33 件 = 約 4% が 404/410 と判明した。AI-Pulse でも entity.history[].url /
entity.modules.future[].url / event.source_url に捏造 URL が混入する経路が同じなので、
ビルド/push 時に URL 生存検証ゲートで物理的に弾く構造を持たせる。

# 設計 (feedback_check_design_principles の 5 段で構造解決)

- 境界 1 箇所集約 (本命): URL 抽出 + HEAD/GET + 判定を本モジュールに寄せ、
  audit_urls.py / tests/test_urls_live.py / runner gate は必ず本モジュールを通す。
- 契約テスト: tests/test_urls_live.py が本モジュールを呼び store 全体を走査。
- エスケープ: 無人環境 (DNS 無し等) で誤発火しないよう AI_PULSE_SKIP_URL_CHECK=1 で全スキップ可能。

# 検証ロジック (News-Grasp validate_deepdive_urls.py と同等の 3 段プローブ)

URL → HEAD ChromeWin (10s) → 200-399 = OK / 404,410 = FATAL → ambiguous なら GET ChromeWin
range → 同様判定 → 更に GET SafariMac range で 1 段。403/405/501 のみ全段継続なら anti-bot
として ambiguous OK (Bloomberg/theinformation 等)。DNS 解決失敗は即 FATAL (捏造ホスト疑い)。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_PKG_ROOT = Path(__file__).resolve().parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

# bot 偽装用 UA。複数 UA で順次探ることで anti-bot を剥がし、隠れた 404 を露出させる。
# News-Grasp 2026-06-03 学習: urllib + Chrome では 403 を返すが Safari UA + Apache では
# 404 を出すサイト (techxplore 等) があり、1 UA だけだと捏造 URL が anti-bot 偽装の裏に
# 隠れて素通りするため、ChromeWin → SafariMac の 2 UA を順に試す。
_UAS = (
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 "
     "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"),
)


@dataclass(frozen=True)
class UrlRef:
    """1 URL 検証単位。location は store 内の出所 (`entity[<id>].history[<i>].url` 等)。"""
    url: str
    location: str


@dataclass(frozen=True)
class UrlVerdict:
    ref: UrlRef
    status: int | None       # HTTP code または None (network error)
    ok: bool                 # True = 生存確認 / False = fatal (捏造または恒久 404)
    detail: str              # 人間向け説明 (404 / DNS 失敗 / 403→GET で 200 等)


class UrlFabricationError(Exception):
    """entities.jsonl / events.jsonl に生存しない URL が含まれる。

    audit_urls.py の --gate モードと契約テスト test_urls_live.py が本例外を hard fail に
    つなぐ。捏造 URL を含むコミット/push を物理的に止める。
    """


def _probe(
    url: str,
    *,
    method: str,
    timeout: float,
    range_header: bool,
    ua: str,
) -> tuple[int | None, str]:
    """HEAD または GET (range) 1 回。(status, detail) を返す。

    ua タグを detail に含めて、どの UA で何が返ったかを後段ログから追える形にする。
    Accept は `*/*` のみに絞る (techxplore 等の Apache 系 WAF は Accept-Language で
    fingerprint してきて、curl 既定の `Accept: */*` のみでないと真の 404 を返さない)。
    """
    ua_tag = "ChromeWin" if "Windows" in ua else "SafariMac" if "Macintosh" in ua else "UA"
    headers = {"User-Agent": ua, "Accept": "*/*"}
    if range_header:
        # 4 KB だけ取得して帯域節約 (HEAD 拒否サイトの再判定用)
        headers["Range"] = "bytes=0-4095"
    try:
        req = urllib.request.Request(url, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), f"{method}[{ua_tag}] {resp.status}"
    except urllib.error.HTTPError as e:
        return int(e.code), f"{method}[{ua_tag}] {e.code}"
    except urllib.error.URLError as e:
        return None, f"{method}[{ua_tag}] URLError: {e.reason}"
    except (TimeoutError, ConnectionError) as e:
        return None, f"{method}[{ua_tag}] {type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001
        return None, f"{method}[{ua_tag}] {type(e).__name__}: {e}"


def _verify_one(ref: UrlRef, *, timeout: float) -> UrlVerdict:
    """1 URL を多段プローブ (HEAD ChromeWin → GET ChromeWin range → GET SafariMac range) で判定する。

    判定方針:
    - 任意の段で **404 / 410 が出たら即 FATAL** (UA 偽装の裏にも見える 404 を露出させる)
    - 任意の段で 200-399 が返れば OK 確定
    - 全段 403/405/501 のみ → anti-bot 継続として ambiguous OK
    - DNS 解決失敗 → 1 段目で FATAL に格上げ (捏造ホスト疑い)
    - その他のネットワークエラーが続く → ambiguous OK (オフライン環境で誤発火させない)
    """
    statuses: list[int | None] = []
    details: list[str] = []

    # 1 段目: HEAD ChromeWin
    s1, d1 = _probe(ref.url, method="HEAD", timeout=timeout, range_header=False, ua=_UAS[0])
    statuses.append(s1); details.append(d1)
    if s1 is not None and 200 <= s1 < 400:
        return UrlVerdict(ref, s1, True, d1)
    if s1 in (404, 410):
        return UrlVerdict(ref, s1, False, d1)
    # DNS 失敗は即 fatal (捏造ホスト疑い)
    if ("getaddrinfo" in d1 or "Name or service not known" in d1
            or "nxdomain" in d1.lower()):
        return UrlVerdict(ref, None, False, f"{d1} (DNS 解決失敗 = 捏造ホスト疑い)")

    # 2 段目: GET range ChromeWin (HEAD 拒否のみ防御している鯖を剥がす)
    s2, d2 = _probe(ref.url, method="GET", timeout=timeout, range_header=True, ua=_UAS[0])
    statuses.append(s2); details.append(d2)
    if s2 is not None and 200 <= s2 < 400:
        return UrlVerdict(ref, s2, True, f"{d1} → {d2} (HEAD 拒否)")
    if s2 in (404, 410):
        return UrlVerdict(ref, s2, False, f"{d1} → {d2}")

    # 3 段目: GET range SafariMac (Chrome UA 拒否の Apache 系を剥がす)
    s3, d3 = _probe(ref.url, method="GET", timeout=timeout, range_header=True, ua=_UAS[1])
    statuses.append(s3); details.append(d3)
    if s3 is not None and 200 <= s3 < 400:
        return UrlVerdict(ref, s3, True, f"{d1} → {d2} → {d3} (Safari UA 必須)")
    if s3 in (404, 410):
        return UrlVerdict(ref, s3, False, f"{d1} → {d2} → {d3}")

    # 全段で 2xx にも 404 にもならず終わった場合
    valid_codes = [s for s in statuses if s is not None]
    if valid_codes:
        if all(s in (403, 405, 501) for s in valid_codes):
            return UrlVerdict(ref, valid_codes[-1], True,
                              f"{' → '.join(details)} (anti-bot 全段継続・ambiguous)")
        return UrlVerdict(ref, valid_codes[-1], False, " → ".join(details))

    # 全段ネットワークエラー (オフライン環境等) → ambiguous OK
    return UrlVerdict(ref, None, True,
                      f"{' / '.join(details)} (network unreachable・ambiguous)")


def verify_urls(
    refs: Iterable[UrlRef],
    *,
    timeout: float = 10.0,
    max_workers: int = 8,
) -> list[UrlVerdict]:
    """URL を並列に検証する。順序は入力順を保持。"""
    refs_list = list(refs)
    if not refs_list:
        return []
    results: dict[int, UrlVerdict] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        fut_to_idx = {ex.submit(_verify_one, r, timeout=timeout): i
                      for i, r in enumerate(refs_list)}
        for fut in as_completed(fut_to_idx):
            results[fut_to_idx[fut]] = fut.result()
    return [results[i] for i in range(len(refs_list))]


# ── 抽出 (entities.jsonl / events.jsonl 構造に特化) ─────────────────────────────

def extract_urls_from_entity(entity: dict) -> list[UrlRef]:
    """1 entity から検証対象 URL を抽出する。

    対象: history[].url, modules.future[].url。
    competitors/relations は文字列 ID なので対象外。overview/positioning の本文中 URL も
    現状の運用では持たないため対象外 (将来 markdown 化されたら拡張する)。
    """
    eid = entity.get("entity_id", "?")
    out: list[UrlRef] = []
    for i, h in enumerate(entity.get("history") or []):
        u = str(h.get("url", "")).strip()
        if u.startswith("http"):
            out.append(UrlRef(url=u, location=f"entity[{eid}].history[{i}]"))
    for i, f in enumerate(((entity.get("modules") or {}).get("future") or [])):
        u = str(f.get("url", "")).strip()
        if u.startswith("http"):
            out.append(UrlRef(url=u, location=f"entity[{eid}].modules.future[{i}]"))
    return out


def extract_urls_from_event(event: dict) -> list[UrlRef]:
    """1 event から検証対象 URL を抽出する。

    対象: source_url のみ (記事本文の出典 URL = 捏造混入経路)。thumb は CDN 画像なので
    URL の捏造性とは別問題 (404 でも画像非表示にしかならない) のため第一弾では対象外。
    """
    evid = event.get("event_id", "?")
    out: list[UrlRef] = []
    u = str(event.get("source_url", "")).strip()
    if u.startswith("http"):
        out.append(UrlRef(url=u, location=f"event[{evid}].source_url"))
    return out


def extract_urls_from_store(
    entities: Iterable[dict],
    events: Iterable[dict],
) -> list[UrlRef]:
    """L1 + L2 から全検証対象 URL を抽出して返す。重複は排除しない (location が違えば別件扱い)。"""
    out: list[UrlRef] = []
    for e in entities:
        out.extend(extract_urls_from_entity(e))
    for v in events:
        out.extend(extract_urls_from_event(v))
    return out


def require_live_urls(
    entities: Iterable[dict],
    events: Iterable[dict],
    *,
    timeout: float = 10.0,
    max_workers: int = 8,
) -> list[UrlVerdict]:
    """store 全体を検証し、fatal が 1 件でもあれば UrlFabricationError を raise する。

    AI_PULSE_SKIP_URL_CHECK=1 環境変数で全スキップ可能 (CI/オフライン環境用)。
    本番 runner / push gate は本変数を立てないので常時 ON のまま。
    """
    if os.environ.get("AI_PULSE_SKIP_URL_CHECK") == "1":
        return []
    refs = extract_urls_from_store(entities, events)
    verdicts = verify_urls(refs, timeout=timeout, max_workers=max_workers)
    fatal = [v for v in verdicts if not v.ok]
    if fatal:
        lines = [
            f"{len(fatal)}/{len(verdicts)} 件の URL が生存検証 NG (捏造 URL または恒久 404)",
            "AI-Pulse の commit/push は URL 生存を強制する (News-Grasp 2026-06-03 三菱UFJ 事故の横展開)。",
        ]
        for v in fatal:
            lines.append(f"  [{v.ref.location}] {v.detail}  {v.ref.url}")
        raise UrlFabricationError("\n".join(lines))
    return verdicts


# ── ヘルパ: jsonl ロード (schema.py に依存せず単独で動かせる) ──────────────────

def load_store(
    entities_path: Path | str = _PKG_ROOT / "data" / "entities.jsonl",
    events_path: Path | str = _PKG_ROOT / "data" / "events.jsonl",
) -> tuple[list[dict], list[dict]]:
    """entities.jsonl と events.jsonl をロードして dict のリストで返す。空行はスキップ。"""
    def _read(p: Path) -> list[dict]:
        if not p.exists():
            return []
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
    return _read(Path(entities_path)), _read(Path(events_path))
