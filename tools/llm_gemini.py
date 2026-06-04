"""Gemini API 薄ラッパ: 記事本文 → summary / summary_points / rationale / score / importance / event_type。

なぜ重要か（意図）:
  Gemini API 呼び出しの境界を 1 つに集約することで:
    1. response_json_schema を schema.gemini_response_schema() の 1 ソースに固定
    2. RPM トークンバケットを 1 箇所で acquire（突発 429 防止）
    3. 失敗時挙動（429/5xx の指数バックオフ・schema 違反の 1 回再投げ・最終ドロップ）を 1 箇所に集約
  collect_rss はここの generate_event_extras を 1 関数呼び出すだけで、リトライ/レート制御を意識しない。
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

PROMPT_PATH = ROOT / "prompts" / "gemini_summarize.md"


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
    """prompts/gemini_summarize.md から system_instruction と user テンプレを取り出す。"""
    text = PROMPT_PATH.read_text(encoding="utf-8")
    # `## system_instruction` 〜 `## user` 〜 EOF
    sys_m = re.search(r"##\s*system_instruction\s*\n(.+?)\n##\s*user\s*\n", text, re.DOTALL)
    usr_m = re.search(r"##\s*user\s*\n(.+)$", text, re.DOTALL)
    if not sys_m or not usr_m:
        raise LLMError(f"prompts/gemini_summarize.md の構造が崩れています")
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
        temperature=0.4,
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


# 強調記法の検出（_check_shape の emphasis チェック用 / contract test の単一ソース）
# 太字 `**X**` / マーカー `==X==` / 下線 `__X__` の各記法を検出する。
_RE_MARK = re.compile(r"==[^=\n]+==")
_RE_UND = re.compile(r"__[^_\n]+__")
_RE_BOLD = re.compile(r"\*\*[^*\n]+\*\*")


class EmphasisShortageError(LLMError):
    """summary / summary_points が太字だけで `==マーカー==` も `__下線__` も含まない違反。

    Gemini プロンプトの「太字だけは禁止」契約に該当。retry instruction で 1 回だけ再要求する。
    """


def _check_shape(payload: dict) -> None:
    """Python 側でも schema 違反を弾く（Gemini が JSON mode を破る稀ケース対策）。

    強調記法 3 種（**太字** / ==マーカー== / __下線__）の使用契約も合わせて検証する:
    - summary + summary_points 全体で `==マーカー==` か `__下線__` のいずれかが 1 つ以上必須。
      太字だけは禁止（プロンプトの「絶対条件 1」に対応）。
    - 強調記法を 1 つも使わない summary も禁止（プロンプトの「絶対条件 2」に対応）。
    違反は EmphasisShortageError → generate_event_extras 側で 1 回だけ retry。
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

    # 強調記法の契約検証（プロンプトの「絶対条件 1/2」に対応）
    text_all = (payload.get("summary") or "") + "\n" + "\n".join(pts)
    has_mark = bool(_RE_MARK.search(text_all))
    has_und = bool(_RE_UND.search(text_all))
    has_bold = bool(_RE_BOLD.search(text_all))
    if not has_bold and not has_mark and not has_und:
        raise EmphasisShortageError(
            "強調記法が 1 つも使われていません。**太字** / ==マーカー== / __下線__ "
            "のいずれかを summary か summary_points に最低 2 箇所入れてください。"
        )
    if not has_mark and not has_und:
        raise EmphasisShortageError(
            "太字 `**X**` だけで `==マーカー==` も `__下線__` も使われていません。"
            "記事に数値・結論・規模があれば `==マーカー==` を、"
            "発表・公開・採用・買収など動作があれば `__下線__` を最低 1 つ入れてください。"
        )


def generate_event_extras(article_text: str, meta: dict) -> dict:
    """記事本文と meta から L2 拡張フィールドを生成。失敗で LLMError。

    リトライ方針:
      - 429 / 5xx / ネットワーク例外: 指数バックオフ（5s, 15s, 45s）で計 GEMINI_MAX_RETRIES + 1 回試行
      - schema 違反（応答形が崩れた）: 「差分を厳密 JSON で出し直して」と 1 回だけ追記して再投げ
      - いずれも尽きたら LLMError を上に投げ、collect_rss 側で当該記事をドロップ
    """
    backoffs = [5.0, 15.0, 45.0][: config.GEMINI_MAX_RETRIES + 1]
    last_err: Exception | None = None
    schema_retry_used = False
    emphasis_retry_used = False
    extra = ""
    attempt_count = 0
    for wait in backoffs:
        attempt_count += 1
        try:
            payload = _call_once(article_text, meta, extra_instruction=extra)
            try:
                _check_shape(payload)
                return payload
            except EmphasisShortageError as emph_err:
                # 強調記法違反は 1 回だけ retry（schema 自体は壊れていないので shape retry とは別カウント）
                if not emphasis_retry_used:
                    emphasis_retry_used = True
                    extra = (
                        f"前回の応答は強調記法違反でした（{emph_err}）。"
                        "summary / summary_points は **太字** だけで埋めず、必ず "
                        "`==マーカー==`（決定打となる数値・結論）か `__下線__`（動作・公開・採用などの動詞句）"
                        "のいずれかを 1 つ以上含めて、3 種記法を意味分けして使い分けてください。"
                        "それ以外（rationale / score / importance / event_type）は前回通りで構いません。"
                    )
                    last_err = emph_err
                    continue
                last_err = emph_err
                break  # emphasis 違反 2 回目は諦め
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
    # 連続違反の最終 raise は last_err の型（特に EmphasisShortageError）を保つ。
    # これで「emphasis 連続違反は EmphasisShortageError でドロップ」契約をテスト側から型で識別できる。
    final_cls = EmphasisShortageError if isinstance(last_err, EmphasisShortageError) else LLMError
    raise final_cls(
        f"Gemini 呼び出しが尽きました（{attempt_count} 回試行）: "
        f"{type(last_err).__name__ if last_err else 'None'}: {last_err}"
    )
