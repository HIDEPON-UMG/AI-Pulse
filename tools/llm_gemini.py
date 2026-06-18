"""Gemini API 薄ラッパ: 記事本文 → summary / summary_points / rationale / score / importance / event_type。

なぜ重要か（意図）:
  Gemini API 呼び出しの境界を 1 つに集約することで:
    1. response_json_schema を schema.gemini_response_schema() の 1 ソースに固定
    2. RPM トークンバケットを 1 箇所で acquire（突発 429 防止）
    3. 失敗時挙動（429/5xx の指数バックオフ・schema 違反の 1 回再投げ・最終ドロップ）を 1 箇所に集約
  collect_rss はここの generate_event_extras を 1 関数呼び出すだけで、リトライ/レート制御を意識しない。

  2026-06-05 (追補11) で本線プロンプトを extract_grounded.md に切替し、強調記法の責務を
  tools/rewrite_emphasis.py へ移譲した（EmphasisShortageError 系統は廃止）。理由は eval 追補10:
  プロンプトでの強調指示は事実忠実性の注意予算を奪う・コード付与（rewrite_emphasis）なら全モデル
  共通で意味分けが locked-in できる。旧プロンプトは prompts/.archive/gemini_summarize.md。
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import config  # noqa: E402
import schema  # noqa: E402
from rate_limiter import TokenBucket  # noqa: E402

PROMPT_PATH = ROOT / "prompts" / "extract_grounded.md"


class LLMError(Exception):
    """Gemini 呼び出しの恒久失敗（リトライ尽き / API キー無し / SDK 例外）。"""


# モジュールスコープのバケット（プロセス内で 1 つ）。テストで差し替え可能。
_bucket: TokenBucket | None = None


def _get_bucket() -> TokenBucket:
    global _bucket
    if _bucket is None:
        _bucket = TokenBucket(rpm=config.GEMINI_RPM)
    return _bucket


def _load_api_key() -> str:
    """環境変数 → AI-Pulse/.env → 例外 の順で API キーを探す。"""
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None
    if load_dotenv:
        load_dotenv(ROOT / ".env")
        key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise LLMError(
            "GEMINI_API_KEY が未設定。AI-Pulse/.env か環境変数で設定してください "
            "（Google AI Studio https://aistudio.google.com/apikey で生成・課金カード不要）"
        )
    return key


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=_load_api_key())
    return _client


def _load_prompt() -> tuple[str, str]:
    """PROMPT_PATH (既定: prompts/extract_grounded.md) から system_instruction と user テンプレを取り出す。"""
    text = PROMPT_PATH.read_text(encoding="utf-8")
    # `## system_instruction` 〜 `## user` 〜 EOF
    sys_m = re.search(r"##\s*system_instruction\s*\n(.+?)\n##\s*user\s*\n", text, re.DOTALL)
    usr_m = re.search(r"##\s*user\s*\n(.+)$", text, re.DOTALL)
    if not sys_m or not usr_m:
        raise LLMError(f"プロンプトファイル {PROMPT_PATH.name} の構造が崩れています")
    return sys_m.group(1).strip(), usr_m.group(1).strip()


def _build_user_prompt(article_text: str, meta: dict) -> str:
    sys_text, user_template = _load_prompt()  # sys は build 側でも使うので返すだけ
    return user_template.format(
        title=meta.get("title", ""),
        publisher_text=article_text,
        entity_name=meta.get("entity_name", ""),
        category=meta.get("category", ""),
        vendor=meta.get("vendor", ""),
        entity_positioning=meta.get("entity_positioning", ""),
    )


def _call_once(article_text: str, meta: dict, *, extra_instruction: str = "") -> dict:
    """Gemini に 1 回投げて JSON を取り出す。schema 違反のチェックは呼び出し側で実施。"""
    sys_text, _ = _load_prompt()
    user = _build_user_prompt(article_text, meta)
    if extra_instruction:
        user = user + "\n\n" + extra_instruction
    cfg = types.GenerateContentConfig(
        system_instruction=sys_text,
        response_mime_type="application/json",
        response_json_schema=schema.gemini_response_schema(),
        # 2026-06-05: 事実忠実性を優先するため 0.4 → 0.1（追補10 eval B でラベル退化が解消した値）。
        temperature=0.1,
    )
    _get_bucket().acquire()
    client = _get_client()
    resp = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=user,
        config=cfg,
    )
    raw = (resp.text or "").strip()
    if not raw:
        raise LLMError("Gemini が空応答")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(f"JSON パース失敗: {exc}: {raw[:200]!r}") from exc


def _check_shape(payload: dict) -> None:
    """Python 側でも schema 違反を弾く（Gemini が JSON mode を破る稀ケース対策）。

    2026-06-05 (追補11): 強調記法の検証は rewrite_emphasis に責務移管したため、ここでは
    キー必須・件数・型・range のみを検証する。EmphasisShortageError は廃止（プロンプトが
    強調記法を要求しないため発生しない）。
    """
    required = ("summary", "summary_points", "rationale", "score", "importance", "event_type")
    missing = [k for k in required if k not in payload]
    if missing:
        raise LLMError(f"応答に必須キー欠落: {missing}")
    pts = payload["summary_points"]
    if not isinstance(pts, list) or not (3 <= len(pts) <= 5):
        raise LLMError(f"summary_points 件数が 3〜5 でない: {len(pts) if isinstance(pts, list) else type(pts).__name__}")
    rat = payload["rationale"]
    if not isinstance(rat, dict) or any(k not in rat or not rat[k] for k in ("importance", "impact", "buzz")):
        raise LLMError(f"rationale の3軸欠落: {rat!r}")
    if payload["importance"] not in schema.IMPORTANCE:
        raise LLMError(f"importance 不正: {payload['importance']!r}")
    if payload["event_type"] not in schema.EVENT_TYPES:
        raise LLMError(f"event_type 不正: {payload['event_type']!r}")
    score = payload["score"]
    if not isinstance(score, int) or not (0 <= score <= 100):
        raise LLMError(f"score 不正: {score!r}")


def generate_event_extras(article_text: str, meta: dict) -> dict:
    """記事本文と meta から L2 拡張フィールドを生成。失敗で LLMError。

    リトライ方針:
      - 429 / 5xx / ネットワーク例外: 指数バックオフ（5s, 15s, 45s）で計 GEMINI_MAX_RETRIES + 1 回試行
      - schema 違反（応答形が崩れた）: 「差分を厳密 JSON で出し直して」と 1 回だけ追記して再投げ
      - いずれも尽きたら LLMError を上に投げ、collect_rss 側で当該記事をドロップ

    2026-06-05 (追補11): 強調記法の検証/retry は廃止（rewrite_emphasis に責務移管）。
    """
    backoffs = [5.0, 15.0, 45.0][: config.GEMINI_MAX_RETRIES + 1]
    last_err: Exception | None = None
    schema_retry_used = False
    extra = ""
    attempt_count = 0
    for wait in backoffs:
        attempt_count += 1
        try:
            payload = _call_once(article_text, meta, extra_instruction=extra)
            try:
                _check_shape(payload)
                return payload
            except LLMError as shape_err:
                if not schema_retry_used:
                    schema_retry_used = True
                    extra = (
                        f"前回の応答は schema 違反でした（{shape_err}）。"
                        "summary / summary_points (3〜5件) / rationale (importance,impact,buzz の3キー) / "
                        "score (0〜100 int) / importance (high|mid|low) / event_type の 6 キーを必ず埋めた "
                        "純粋な JSON だけを返してください。前置きや code fence は不可。"
                    )
                    last_err = shape_err
                    continue
                last_err = shape_err
                break  # schema 違反 2 回目は諦め
        except LLMError:
            raise
        except Exception as exc:
            # SDK が投げる ServerError / ClientError 等。文字列で 429/5xx 判定する
            msg = str(exc)
            last_err = exc
            transient = any(t in msg for t in ("429", "500", "502", "503", "504", "RESOURCE_EXHAUSTED", "UNAVAILABLE"))
            if transient and attempt_count < len(backoffs):
                time.sleep(wait)
                continue
            break
    raise LLMError(
        f"Gemini 呼び出しが尽きました（{attempt_count} 回試行）: "
        f"{type(last_err).__name__ if last_err else 'None'}: {last_err}"
    )


def _quality_audit_schema() -> dict:
    """Flash-Lite 監査の JSON schema。候補は自動適用せずログに残す。"""
    return {
        "type": "object",
        "required": ["status", "issues", "term_candidates", "notes"],
        "properties": {
            "status": {"type": "string", "enum": ["ok", "warn", "fail"]},
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["category", "severity", "field", "evidence", "suggestion"],
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": ["translation", "overclaim", "hallucination", "style"],
                        },
                        "severity": {"type": "string", "enum": ["low", "mid", "high"]},
                        "field": {"type": "string"},
                        "evidence": {"type": "string"},
                        "suggestion": {"type": "string"},
                    },
                },
            },
            "term_candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["bad", "good", "reason", "kind"],
                    "properties": {
                        "bad": {"type": "string"},
                        "good": {"type": "string"},
                        "reason": {"type": "string"},
                        "kind": {"type": "string", "enum": ["phrase", "regex", "soften", "warn"]},
                    },
                },
            },
            "notes": {"type": "string"},
        },
    }


def audit_event_quality(article_text: str, event: dict) -> dict:
    """採用済み event の要約品質を Flash-Lite で監査する。

    本文に照らして、誤訳・誇張・本文にない主張を検出する。戻り値は観測ログ専用で、
    event 本体や editorial_terms.json を自動更新しない。
    """
    points = "\n".join(f"- {p}" for p in event.get("summary_points") or [])
    rationale = event.get("rationale") or {}
    user = (
        "あなたは AI-Pulse の編集監査者です。記事本文と生成済み event を比較し、"
        "日本語の自然さ、誤訳、誇張表現、本文にない主張だけを確認してください。\n"
        "厳しすぎる文体好みは issue にせず、読者に誤認を与えるものだけを指摘します。\n"
        "辞書化できる修正があれば term_candidates に追加します。候補は自動適用されないため、"
        "短く再利用しやすい形にしてください。\n\n"
        "[判定]\n"
        "- ok: 問題なし\n"
        "- warn: 表現改善・軽微な誤訳候補あり\n"
        "- fail: 本文にない主張、重大な誤訳、強い誇張がある\n\n"
        "[記事本文]\n"
        f"{article_text[: config.QUALITY_AUDIT_MAX_BODY_CHARS]}\n\n"
        "[event]\n"
        f"event_id: {event.get('event_id', '')}\n"
        f"headline: {event.get('headline', '')}\n"
        f"headline_ja: {event.get('headline_ja', '')}\n"
        f"summary: {event.get('summary', '')}\n"
        f"summary_points:\n{points}\n"
        f"rationale.importance: {rationale.get('importance', '')}\n"
        f"rationale.impact: {rationale.get('impact', '')}\n"
        f"rationale.buzz: {rationale.get('buzz', '')}\n\n"
        "純粋な JSON だけを返してください。"
    )
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=_quality_audit_schema(),
        temperature=0.0,
    )
    _get_bucket().acquire()
    try:
        resp = _get_client().models.generate_content(
            model=config.QUALITY_AUDIT_MODEL,
            contents=user,
            config=cfg,
        )
    except Exception as exc:
        raise LLMError(f"Gemini audit_event_quality 失敗: {exc}") from exc
    raw = (resp.text or "").strip()
    if not raw:
        raise LLMError("Gemini が空応答 (audit_event_quality)")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(f"JSON パース失敗 (audit_event_quality): {exc}: {raw[:200]!r}") from exc
    return payload


def regenerate_rationale(
    headline: str,
    summary: str,
    summary_points: list[str],
    importance_label: str,
    *,
    entity_context: dict | None = None,
) -> dict:
    """既存 event の headline/summary/summary_points/importance ラベルから rationale 3 軸を再生成。

    llm_local.regenerate_rationale と同契約 (collect_rss 側は llm_hybrid 経由で 1 関数として扱える)。
    Gemini structured outputs で rationale 3 キー必須 + minLength=20 を schema 拘束し、Python 側で
    も _check_shape 相当の長さ検証を行って schema 違反は 1 回だけ追記 retry する。
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
    user_base = (
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
    rationale_schema = {
        "type": "object",
        "required": ["importance", "impact", "buzz"],
        "properties": {
            "importance": {"type": "string", "minLength": 20},
            "impact": {"type": "string", "minLength": 20},
            "buzz": {"type": "string", "minLength": 20},
        },
    }
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=rationale_schema,
        temperature=0.2,
    )
    extra = ""
    schema_retry_used = False
    last_err: Exception | None = None
    for attempt in range(2):  # 1 回 + 1 回 schema retry
        user = user_base + (("\n\n" + extra) if extra else "")
        _get_bucket().acquire()
        try:
            resp = _get_client().models.generate_content(
                model=config.GEMINI_MODEL,
                contents=user,
                config=cfg,
            )
        except Exception as exc:
            raise LLMError(f"Gemini regenerate_rationale 失敗: {exc}") from exc
        raw = (resp.text or "").strip()
        if not raw:
            last_err = LLMError("Gemini が空応答 (regenerate_rationale)")
            break
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            last_err = LLMError(f"JSON パース失敗 (regenerate_rationale): {exc}: {raw[:200]!r}")
            break
        missing = [k for k in ("importance", "impact", "buzz")
                   if not (isinstance(payload.get(k), str) and len(payload[k]) >= 20)]
        if not missing:
            return payload
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
    raise LLMError(
        f"Gemini regenerate_rationale が尽きました: "
        f"{type(last_err).__name__ if last_err else 'None'}: {last_err}"
    )


def translate_headline_ja(
    headline: str,
    *,
    entity_context: dict | None = None,
) -> str:
    """英語 headline を短い日本語要約見出しにする（固有名詞は英語のまま）。失敗で LLMError。

    意図:
      collect_rss.py で新規 entry の headline が ASCII 比率 0.95+ の場合だけ呼び、
      生成した文字列を ev["headline_ja"] に格納する。TODAY'S THEME (h1) や各カードの
      .headline-ja DOM 表示で UI が拾う。長い直訳ではなく 28〜42 字目安の要約にする。

    Args:
        headline: 元の英語 headline
        entity_context: {"entity_name": str, "vendor": str, ...}（固有名詞ヒント・任意）

    Returns:
        日本語要約見出し（28〜42 字目安・装飾記号なし・1 行）
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
    cfg = types.GenerateContentConfig(
        response_mime_type="text/plain",
        temperature=0.2,
    )
    _get_bucket().acquire()
    client = _get_client()
    try:
        resp = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=user,
            config=cfg,
        )
    except Exception as exc:
        raise LLMError(f"Gemini translate_headline_ja 失敗: {exc}") from exc
    text = (resp.text or "").strip()
    if not text:
        raise LLMError("Gemini が空応答 (translate_headline_ja)")
    return text.replace("\n", " ").strip().strip('"').strip("'").strip()


def translate_buzzpost_text_ja(text: str) -> str:
    """BuzzPost の英語本文を自然な日本語へ翻訳する。失敗で LLMError。"""
    user = (
        "次のX投稿本文を日本語に翻訳してください。URL、@handle、#hashtag、製品名、会社名、"
        "モデル名は原文のまま残してください。改行は元の読みやすさに近い形で維持し、"
        "説明や前置きは付けず、翻訳本文だけを返してください。\n\n"
        f"{text}"
    )
    cfg = types.GenerateContentConfig(
        response_mime_type="text/plain",
        temperature=0.2,
    )
    _get_bucket().acquire()
    client = _get_client()
    try:
        resp = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=user,
            config=cfg,
        )
    except Exception as exc:
        raise LLMError(f"Gemini translate_buzzpost_text_ja 失敗: {exc}") from exc
    translated = (resp.text or "").strip()
    if not translated:
        raise LLMError("Gemini が空応答 (translate_buzzpost_text_ja)")
    return translated.strip().strip('"').strip("'").strip()
