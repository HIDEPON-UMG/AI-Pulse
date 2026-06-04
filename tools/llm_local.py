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
