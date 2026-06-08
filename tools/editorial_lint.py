"""AI-Pulse の編集用語 lint。

LLM 出力後の日本語に対して、ニュース翻訳の固定訳と誇張表現の抑制を決定論で適用する。
外部 CAT ツールを直接組み込まず、termbase / Vale substitution に近い小さな境界として扱う。
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TERMS_PATH = ROOT / "data" / "editorial_terms.json"

TEXT_FIELDS = ("summary",)
RATIONALE_FIELDS = ("importance", "impact", "buzz")


def _load_terms(path: Path = DEFAULT_TERMS_PATH) -> dict:
    """用語集 JSON を読む。存在しない場合は空ルールとして扱う。"""
    if not path.exists():
        return {"phrase_replacements": [], "soften_replacements": [], "warn_patterns": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _apply_replacements(text: str, rules: list[dict], *, kind: str) -> tuple[str, list[dict]]:
    """単純な文字列置換を適用し、適用結果を findings として返す。"""
    findings: list[dict] = []
    out = text
    for rule in rules:
        bad = rule.get("bad")
        good = rule.get("good")
        if not (isinstance(bad, str) and isinstance(good, str) and bad):
            continue
        if bad in out:
            count = out.count(bad)
            out = out.replace(bad, good)
            findings.append({
                "kind": kind,
                "bad": bad,
                "good": good,
                "count": count,
                "note": rule.get("note", ""),
            })
    return out, findings


def _apply_regex_replacements(text: str, rules: list[dict]) -> tuple[str, list[dict]]:
    """正規表現置換を適用し、適用結果を findings として返す。"""
    findings: list[dict] = []
    out = text
    for rule in rules:
        pattern = rule.get("pattern")
        good = rule.get("good")
        if not (isinstance(pattern, str) and isinstance(good, str)):
            continue
        try:
            out_new, count = re.subn(pattern, good, out)
        except re.error:
            continue
        if count:
            out = out_new
            findings.append({
                "kind": "regex_replacement",
                "pattern": pattern,
                "good": good,
                "count": count,
                "note": rule.get("note", ""),
            })
    return out, findings


def _warn_patterns(text: str, rules: list[dict]) -> list[dict]:
    """注意喚起用の正規表現を検出する。本文は変更しない。"""
    findings: list[dict] = []
    for rule in rules:
        pat = rule.get("pattern")
        if not isinstance(pat, str):
            continue
        try:
            matches = re.findall(pat, text)
        except re.error:
            continue
        if matches:
            findings.append({
                "kind": "warn",
                "pattern": pat,
                "count": len(matches),
                "message": rule.get("message", ""),
            })
    return findings


def _rewrite_text(text: str, terms: dict) -> tuple[str, list[dict]]:
    findings: list[dict] = []
    out, got = _apply_regex_replacements(text, terms.get("regex_replacements", []))
    findings.extend(got)
    out, got = _apply_replacements(
        out, terms.get("phrase_replacements", []), kind="phrase_replacement"
    )
    findings.extend(got)
    out, got = _apply_replacements(
        out, terms.get("soften_replacements", []), kind="soften_replacement"
    )
    findings.extend(got)
    findings.extend(_warn_patterns(out, terms.get("warn_patterns", [])))
    return out, findings


def apply_editorial_lint(extras: dict[str, Any], *, terms_path: Path = DEFAULT_TERMS_PATH) -> tuple[dict, list[dict]]:
    """LLM extras に編集用語 lint を適用し、(修正後 extras, findings) を返す。

    入力 dict は破壊しない。summary / summary_points / rationale のみを対象にする。
    """
    terms = _load_terms(terms_path)
    out = copy.deepcopy(extras)
    findings: list[dict] = []

    for field in TEXT_FIELDS:
        if isinstance(out.get(field), str):
            out[field], got = _rewrite_text(out[field], terms)
            findings.extend({"field": field, **g} for g in got)

    points = out.get("summary_points")
    if isinstance(points, list):
        rewritten = []
        for i, point in enumerate(points):
            if isinstance(point, str):
                new_point, got = _rewrite_text(point, terms)
                findings.extend({"field": f"summary_points[{i}]", **g} for g in got)
                rewritten.append(new_point)
            else:
                rewritten.append(point)
        out["summary_points"] = rewritten

    rationale = out.get("rationale")
    if isinstance(rationale, dict):
        for key in RATIONALE_FIELDS:
            if isinstance(rationale.get(key), str):
                rationale[key], got = _rewrite_text(rationale[key], terms)
                findings.extend({"field": f"rationale.{key}", **g} for g in got)

    return out, findings
