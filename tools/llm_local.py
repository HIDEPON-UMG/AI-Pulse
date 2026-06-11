"""Ollama (ローカル) 薄ラッパ: 記事本文 → summary / summary_points / rationale / score / importance / event_type。

なぜ重要か（意図）:
  llm_gemini.generate_event_extras と **同じ契約** (article_text, meta) -> dict を満たすローカル版バックエンド。
  プロンプト・スキーマ・shape 検証は llm_gemini / schema から再利用し、API 呼び出し部分だけ Ollama /api/chat に
  差し替える。こうすることで「抽出 LLM の境界」を二重化せず、本番切替は collect_rss の import 先を 1 行替える
  だけで済む（feedback_check_design_principles §2「境界 1 箇所集約」）。

  qwen3 は thinking モデルのため think=false 必須（付けないと本文が空になる）。Ollama の structured outputs
  (`format` に JSON Schema を渡す) で schema 拘束も効く。クォータ非依存・オフライン自走が狙いで、コスト削減は
  動機にならない（flash-lite が既に $0.015/76件）。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import config  # noqa: E402
import schema  # noqa: E402
import llm_gemini  # noqa: E402  # プロンプト整形 / shape 検証 / 例外型を再利用（境界の二重化を避ける）

# 例外型は Gemini 版と共有する（collect_rss 側は LLMError 1 種だけ捕捉すればよい）。
LLMError = llm_gemini.LLMError


def _call_once(article_text: str, meta: dict, *, extra_instruction: str = "") -> dict:
    """Ollama /api/chat に 1 回投げて JSON を取り出す。shape チェックは呼び出し側で実施。"""
    sys_text, _ = llm_gemini._load_prompt()
    user = llm_gemini._build_user_prompt(article_text, meta)
    if extra_instruction:
        user = user + "\n\n" + extra_instruction
    req = {
        "model": config.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": sys_text},
            {"role": "user", "content": user},
        ],
        "think": False,  # qwen3 は thinking モデル。false にしないと本文（JSON）が出ない
        "format": schema.gemini_response_schema(),  # structured outputs で schema 拘束
        "stream": False,
        "options": {"temperature": config.OLLAMA_TEMPERATURE},
    }
    data = json.dumps(req).encode("utf-8")
    url = f"{config.OLLAMA_HOST}/api/chat"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}),
            timeout=config.OLLAMA_TIMEOUT_SEC,
        ) as r:
            resp = json.load(r)
    except urllib.error.URLError as exc:
        raise LLMError(f"Ollama 接続失敗（{url} は起動済みか？）: {exc}") from exc
    raw = (resp.get("message", {}).get("content") or "").strip()
    if not raw:
        raise LLMError("Ollama が空応答（think=false が効いているか / モデルロード失敗を疑う）")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(f"JSON パース失敗: {exc}: {raw[:200]!r}") from exc


def generate_event_extras(article_text: str, meta: dict) -> dict:
    """記事本文と meta から L2 拡張フィールドを生成。失敗で LLMError（llm_gemini と同契約）。

    リトライ方針（ローカルは RPM 制限が無いので Gemini 版より単純）:
      - 接続失敗 / 空応答 / JSON パース失敗: 短バックオフ（2s）で計 OLLAMA_MAX_RETRIES + 1 回試行
      - schema 違反（応答形が崩れた）: 「厳密 JSON で出し直して」と 1 回だけ追記して再投げ
      - いずれも尽きたら LLMError を上に投げ、呼び出し側で当該記事をドロップ
    """
    attempts = config.OLLAMA_MAX_RETRIES + 1
    last_err: Exception | None = None
    schema_retry_used = False
    extra = ""
    attempt = 0
    while attempt < attempts:
        attempt += 1
        try:
            payload = _call_once(article_text, meta, extra_instruction=extra)
        except LLMError as exc:
            # 接続/空応答/パース失敗 → transient とみなし短バックオフ再試行
            last_err = exc
            if attempt < attempts:
                time.sleep(2.0)
                continue
            break
        try:
            llm_gemini._check_shape(payload)
            return payload
        except LLMError as shape_err:
            last_err = shape_err
            if not schema_retry_used:
                schema_retry_used = True
                extra = (
                    f"前回の応答は schema 違反でした（{shape_err}）。"
                    "summary / summary_points (3〜5件) / rationale (importance,impact,buzz の3キー) / "
                    "score (0〜100 int) / importance (high|mid|low) / event_type の 6 キーを必ず埋めた "
                    "純粋な JSON だけを返してください。前置きや code fence は不可。"
                )
                continue
            break  # schema 違反 2 回目は諦め
    raise LLMError(
        f"Ollama 呼び出しが尽きました（{attempt} 回試行）: "
        f"{type(last_err).__name__ if last_err else 'None'}: {last_err}"
    )


def generate_carte_fields(entity: dict, recent_events: list[dict]) -> dict:
    """既存 entity と直近 event からカルテ更新差分を Ollama で生成する。

    NotebookLM の外部 research 依存を外し、AI-Pulse が既に採用済みの event と
    現在の entity 情報だけを根拠に overview と self 列の比較セルを更新する。
    競合列や logo などの既存構造は呼び出し側で保持する。
    """
    axes = schema.LENS_AXES.get(entity.get("category"), [])
    axis_keys = [axis["key"] for axis in axes]
    if not axis_keys:
        raise LLMError(f"カルテ軸が未定義です: category={entity.get('category')!r}")
    event_lines = []
    for ev in recent_events[:8]:
        points = ev.get("summary_points") or []
        point_text = " / ".join(str(p) for p in points[:3])
        event_lines.append(
            "\n".join(
                [
                    f"- date: {ev.get('date', '')}",
                    f"  headline: {ev.get('headline_ja') or ev.get('headline', '')}",
                    f"  summary: {ev.get('summary', '')}",
                    f"  points: {point_text}",
                    f"  source: {ev.get('source', '')}",
                ]
            )
        )
    events_text = "\n".join(event_lines) or "- 新規 event なし"
    axis_text = "\n".join(f"- {axis['key']}: {axis['label']}" for axis in axes)
    current_overview = entity.get("overview") or entity.get("positioning") or ""
    user = (
        "あなたは AI-Pulse のカルテ編集者です。NotebookLM は使わず、下の既存カルテ情報と"
        "AI-Pulse に採用済みの直近 event だけを根拠に、カルテ更新差分を作ってください。\n\n"
        "[対象 entity]\n"
        f"entity_id: {entity.get('entity_id')}\n"
        f"name: {entity.get('name')}\n"
        f"vendor: {entity.get('vendor')}\n"
        f"category: {entity.get('category')}\n"
        f"positioning: {entity.get('positioning')}\n"
        f"current_overview: {current_overview}\n\n"
        "[直近 event]\n"
        f"{events_text}\n\n"
        "[比較軸]\n"
        f"{axis_text}\n\n"
        "[出力規約]\n"
        "- overview は 3〜5 文の日本語。固有名詞は英語のまま残す。\n"
        "- cells は比較軸 key をすべて含む object。各値は 1〜2 文、または短い文字列配列。\n"
        "- 入力にない未確認事実、価格、日付、性能値を作らない。\n"
        "- 不明な軸は N/A と書く。空文字は禁止。\n"
        "- 純粋な JSON だけを返す。前置き・後置き・code fence は不可。"
    )
    carte_schema = {
        "type": "object",
        "required": ["overview", "cells"],
        "properties": {
            "overview": {"type": "string", "minLength": 20},
            "cells": {
                "type": "object",
                "required": axis_keys,
                "properties": {
                    key: {
                        "oneOf": [
                            {"type": "string", "minLength": 1},
                            {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string", "minLength": 1},
                            },
                        ]
                    }
                    for key in axis_keys
                },
            },
        },
    }
    attempts = config.OLLAMA_MAX_RETRIES + 1
    last_err: Exception | None = None
    extra = ""
    for attempt in range(1, attempts + 1):
        req = {
            "model": config.OLLAMA_MODEL,
            "messages": [{"role": "user", "content": user + (("\n\n" + extra) if extra else "")}],
            "think": False,
            "format": carte_schema,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        data = json.dumps(req).encode("utf-8")
        url = f"{config.OLLAMA_HOST}/api/chat"
        try:
            with urllib.request.urlopen(
                urllib.request.Request(
                    url, data=data, headers={"Content-Type": "application/json"}
                ),
                timeout=config.OLLAMA_TIMEOUT_SEC,
            ) as r:
                resp = json.load(r)
            raw = (resp.get("message", {}).get("content") or "").strip()
            if not raw:
                raise LLMError("Ollama が空応答 (generate_carte_fields / think=false 確認)")
            payload = json.loads(raw)
            _check_carte_shape(payload, axis_keys)
            return payload
        except (urllib.error.URLError, json.JSONDecodeError, LLMError) as exc:
            last_err = exc
            extra = (
                f"前回の応答はカルテ schema 違反または取得失敗でした: {exc}。"
                "overview と cells を必ず埋め、cells には指定された全 key を含めてください。"
            )
            if attempt < attempts:
                time.sleep(2.0)
    raise LLMError(
        f"Ollama カルテ生成が尽きました（{attempts} 回試行）: "
        f"{type(last_err).__name__ if last_err else 'None'}: {last_err}"
    )


def _check_carte_shape(payload: dict, axis_keys: list[str]) -> None:
    """Ollama カルテ応答の最低限 shape を検証する。"""
    if not isinstance(payload, dict):
        raise LLMError("カルテ応答が object ではありません")
    if not isinstance(payload.get("overview"), str) or not payload["overview"].strip():
        raise LLMError("カルテ overview が空です")
    cells = payload.get("cells")
    if not isinstance(cells, dict):
        raise LLMError("カルテ cells が object ではありません")
    missing = [key for key in axis_keys if key not in cells]
    if missing:
        raise LLMError(f"カルテ cells の軸欠落: {missing}")
    for key in axis_keys:
        value = cells[key]
        if isinstance(value, str) and value.strip():
            continue
        if (
            isinstance(value, list)
            and value
            and all(isinstance(item, str) and item.strip() for item in value)
        ):
            continue
        raise LLMError(f"カルテ cells[{key!r}] が空または不正です")


def regenerate_rationale(
    headline: str,
    summary: str,
    summary_points: list[str],
    importance_label: str,
    *,
    entity_context: dict | None = None,
) -> dict:
    """既存 event の headline/summary/summary_points/importance ラベルから rationale 3 軸を再生成。

    なぜ重要か (意図):
      collect_rss 段階の generate_event_extras と異なり、article_text が手元に無い既存 event の
      rationale を「文章」として再生成する境界。Part 7 で schema が rationale 各値 20 字以上を
      強制したため、既存 events.jsonl の 72 件「単語のみ rationale」を一括補正するための専用関数。

      Ollama /api/chat に structured outputs (3 キー必須 + minLength=20) で 1 ショット投入し、
      schema 違反は 1 回だけ「厳密 JSON で出し直して」を追記して再投げ。失敗は LLMError で
      llm_hybrid 層に投げ、Gemini フォールバックに任せる。

    Args:
        headline: イベント見出し（rationale の根拠材料）
        summary: 160-240 字の要約（最も情報量が多い）
        summary_points: 3-5 件の要点（多角的根拠）
        importance_label: 既存 importance ラベル（"high"/"mid"/"low"）。なぜそのラベルと判定したかを文章で説明させる
        entity_context: 任意。entity_name / vendor / name を「固有名詞ヒント」として渡す

    Returns:
        {"importance": str, "impact": str, "buzz": str} の dict。各値 20 字以上を schema で保証。

    Raises:
        LLMError: 接続失敗 / schema 違反 2 回 / JSON パース失敗
    """
    ctx_hints = ""
    if entity_context:
        names = [
            str(entity_context.get(k, "")) for k in ("entity_name", "vendor", "name")
        ]
        names = [n for n in names if n]
        if names:
            ctx_hints = f"\n固有名詞ヒント（英語のまま残してよい）: {', '.join(names)}"
    bullets = "\n".join(f"- {p}" for p in summary_points)
    user = (
        "あなたは AI-Pulse の編集者です。以下の event 情報から、判断理由 rationale を 3 軸"
        "(importance, impact, buzz) で再生成してください。\n\n"
        "[event 情報]\n"
        f"headline: {headline}\n"
        f"summary: {summary}\n"
        f"summary_points:\n{bullets}\n"
        f"importance ラベル: {importance_label}\n"
        f"{ctx_hints}\n\n"
        "[出力規約]\n"
        f"- importance: なぜ重要度を {importance_label} と判定したか、本文記述に基づき 40〜80 字で具体的に説明\n"
        "- impact: 影響度の根拠（波及範囲・規模）を 40〜80 字で具体的に説明\n"
        "- buzz: 話題性の根拠（出典格・コミュニティ注目）を 40〜80 字で具体的に説明\n"
        "- **\"high\"/\"mid\"/\"low\" など値ラベルを反復するだけの記述は禁止**\n"
        "- 各値は最低 20 字以上の文章（短すぎる応答は schema 違反で弾かれる）\n"
        "- 装飾記号（マーカー・太字・下線）は使わない\n\n"
        "純粋な JSON だけを返してください（前置き・後置き・コードブロック禁止）。"
    )
    # 専用 schema (rationale 3 キーのみ / 各 minLength=20)
    rationale_schema = {
        "type": "object",
        "required": ["importance", "impact", "buzz"],
        "properties": {
            "importance": {"type": "string", "minLength": 20},
            "impact": {"type": "string", "minLength": 20},
            "buzz": {"type": "string", "minLength": 20},
        },
    }
    attempts = config.OLLAMA_MAX_RETRIES + 1
    last_err: Exception | None = None
    schema_retry_used = False
    extra = ""
    attempt = 0
    while attempt < attempts:
        attempt += 1
        req = {
            "model": config.OLLAMA_MODEL,
            "messages": [{"role": "user", "content": user + (("\n\n" + extra) if extra else "")}],
            "think": False,
            "format": rationale_schema,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        data = json.dumps(req).encode("utf-8")
        url = f"{config.OLLAMA_HOST}/api/chat"
        try:
            with urllib.request.urlopen(
                urllib.request.Request(
                    url, data=data, headers={"Content-Type": "application/json"}
                ),
                timeout=config.OLLAMA_TIMEOUT_SEC,
            ) as r:
                resp = json.load(r)
        except urllib.error.URLError as exc:
            last_err = LLMError(f"Ollama 接続失敗 (regenerate_rationale, {url}): {exc}")
            if attempt < attempts:
                time.sleep(2.0)
                continue
            break
        raw = (resp.get("message", {}).get("content") or "").strip()
        if not raw:
            last_err = LLMError("Ollama が空応答 (regenerate_rationale / think=false 確認)")
            if attempt < attempts:
                time.sleep(2.0)
                continue
            break
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            last_err = LLMError(f"JSON パース失敗 (regenerate_rationale): {exc}: {raw[:200]!r}")
            if attempt < attempts:
                time.sleep(2.0)
                continue
            break
        # shape チェック (schema 違反は 1 度だけ追記 retry)
        missing = [k for k in ("importance", "impact", "buzz")
                   if not (isinstance(payload.get(k), str) and len(payload[k]) >= 20)]
        if missing:
            last_err = LLMError(f"rationale schema 違反 (短すぎ/欠落): {missing}")
            if not schema_retry_used:
                schema_retry_used = True
                extra = (
                    f"前回の応答は schema 違反でした: {missing} が 20 字未満または欠落。"
                    "3 キー (importance, impact, buzz) すべてに 40〜80 字の文章を必ず埋めた "
                    "純粋な JSON だけを返してください。"
                )
                continue
            break
        return payload
    raise LLMError(
        f"Ollama 呼び出しが尽きました (regenerate_rationale / {attempt} 回試行): "
        f"{type(last_err).__name__ if last_err else 'None'}: {last_err}"
    )


def translate_headline_ja(
    headline: str,
    *,
    entity_context: dict | None = None,
) -> str:
    """英語 headline を短い日本語要約見出しにする。llm_gemini.translate_headline_ja と同契約。

    Ollama /api/chat に 1 ショットで投げる（リトライなし。失敗即 LLMError → hybrid 層で Gemini fallback）。
    structured outputs は使わず純テキスト応答（短文・装飾不要のため）。
    """
    ctx_hints = ""
    if entity_context:
        names = [
            str(entity_context.get(k, "")) for k in ("entity_name", "vendor", "name")
        ]
        names = [n for n in names if n]
        if names:
            ctx_hints = f"\n固有名詞ヒント（英語のまま残す）: {', '.join(names)}"
    user = (
        "次の英語見出しを、直訳ではなく 28〜42 字程度の自然な日本語要約見出しにしてください。"
        "会社名・製品名・人名などの固有名詞はそのまま英語表記で残し、それ以外（動詞・名詞・"
        "形容詞・前置詞など）は日本語にしてください。長い修飾句は要約し、末尾に「…」を付けない。"
        "装飾記号（マーカー・太字）は付けない。純粋な日本語見出しだけを 1 行で返してください"
        "（前置き・引用符・code fence は不可）。"
        f"\n\n英語見出し: {headline}"
        f"{ctx_hints}"
    )
    req = {
        "model": config.OLLAMA_MODEL,
        "messages": [{"role": "user", "content": user}],
        "think": False,
        "stream": False,
        "options": {"temperature": 0.2},
    }
    data = json.dumps(req).encode("utf-8")
    url = f"{config.OLLAMA_HOST}/api/chat"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            ),
            timeout=config.OLLAMA_TIMEOUT_SEC,
        ) as r:
            resp = json.load(r)
    except urllib.error.URLError as exc:
        raise LLMError(
            f"Ollama 接続失敗 (translate_headline_ja, {url}): {exc}"
        ) from exc
    text = (resp.get("message", {}).get("content") or "").strip()
    if not text:
        raise LLMError("Ollama が空応答 (translate_headline_ja / think=false 確認)")
    return text.replace("\n", " ").strip().strip('"').strip("'").strip()
