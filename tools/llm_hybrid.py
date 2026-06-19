"""ハイブリッド LLM ファサード: ローカル (Ollama Qwen3.6-27B IQ3_XXS) を通常パスに、失敗時のみ Gemini フォールバック。

なぜ重要か（意図）:
  Gemini API Free Tier は (a) RPD/RPM クォータ天井と (b) Google 学習データへの利用 という
  非コスト面のリスクがあり、AI-Pulse の本番抽出パスではローカル LLM を優先したい。一方で
  Ollama サーバ落ち / モデル未ロードで止まると bot 全体が止まるため、Gemini を「安全網」
  として残す。

  境界を 1 関数 (generate_event_extras) に集約し、切替を HYBRID_MODE で可逆化する
  ([[feedback_check_design_principles]] §2「境界 1 箇所集約」)。class of bug は
  tests/test_llm_hybrid.py で locked-in（§4「契約テスト 1 件で不変条件」）。

  collect_rss は llm_hybrid.generate_event_extras を 1 回呼ぶだけで、フォールバック判断 /
  例外整理を意識しない（呼出側は依然 LLMError 1 種だけ捕捉する）。

設計上の注意:
  - llm_local が `LLMError` を投げたら即フォールバック（hybrid 層では追加リトライしない。
    バックオフは llm_local 側で OLLAMA_MAX_RETRIES 回済んでいる）。
  - 2026-06-07 改定: GPU 占有事前判定 (_gpu_busy / nvidia-smi プローブ) を撤廃した。
    旧実装は「GPU 全体 VRAM が閾値超なら local をスキップして即 Gemini」だったが、
    (1) Ollama 自身のモデル常駐 (~10-12GB) や (2) 瞬間的な他タスク占有を「占有」と誤検出し、
    GPU が空いていてもフォールバック率 96.7% (2026-06-07 実測 / 想定 20%) に張り付いた。
    「占有を事前推測する」という誤りうる状態自体を消し、常に local を 1 度試して Ollama が
    OOM/接続失敗/空応答で LLMError を返した時のみ Gemini に落とす（事実ベース・可逆）。
    Ollama が VRAM 不足ならモデルロードを自前で evict して LLMError になるので安全側
    ([[feedback_check_design_principles]] §1「illegal state unrepresentable」)。
  - HYBRID_MODE=gemini_only は Ollama 全停止時の暫定回避用。
  - HYBRID_MODE=local_only は Gemini を絶対呼ばせたくない時の locked-in（テスト・実験用）。
"""
from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import config  # noqa: E402
import llm_gemini  # noqa: E402
import llm_local  # noqa: E402

LOG_DIR = ROOT / "_logs"

# 呼出側は llm_hybrid.LLMError 1 種だけ捕捉すればよい（llm_gemini.LLMError と同一実体）。
LLMError = llm_gemini.LLMError


def _format_error(exc: BaseException | None) -> str | None:
    if exc is None:
        return None
    return f"{type(exc).__name__}: {exc}"


def _route_log_path(now: datetime | None = None) -> Path:
    now = now or datetime.now()
    return LOG_DIR / f"llm_routes_{now:%Y%m%d}.jsonl"


def _write_route_record(record: dict[str, Any]) -> None:
    """LLM route の観測ログを追記する。失敗しても本線の生成結果は壊さない。"""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with _route_log_path().open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError as exc:
        print(f"LLM route telemetry write failed: {exc}", file=sys.stderr)


def _record_route(
    *,
    mode: str,
    function: str,
    final_backend: str | None,
    fallback_used: bool,
    local_error: BaseException | None,
    gemini_error: BaseException | None,
    started_at: float,
) -> None:
    _write_route_record(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "function": function,
            "final_backend": final_backend,
            "fallback_used": fallback_used,
            "local_error": _format_error(local_error),
            "gemini_error": _format_error(gemini_error),
            "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
        }
    )


def _call_with_route(
    *,
    function: str,
    local_call: Callable[[], Any],
    gemini_call: Callable[[], Any],
) -> Any:
    mode = config.HYBRID_MODE
    started_at = time.perf_counter()
    local_error: BaseException | None = None
    gemini_error: BaseException | None = None

    if mode == "gemini_only":
        try:
            result = gemini_call()
        except LLMError as exc:
            gemini_error = exc
            _record_route(
                mode=mode,
                function=function,
                final_backend=None,
                fallback_used=False,
                local_error=None,
                gemini_error=gemini_error,
                started_at=started_at,
            )
            raise
        _record_route(
            mode=mode,
            function=function,
            final_backend="gemini",
            fallback_used=False,
            local_error=None,
            gemini_error=None,
            started_at=started_at,
        )
        return result

    if mode == "local_only":
        try:
            result = local_call()
        except LLMError as exc:
            local_error = exc
            _record_route(
                mode=mode,
                function=function,
                final_backend=None,
                fallback_used=False,
                local_error=local_error,
                gemini_error=None,
                started_at=started_at,
            )
            raise
        _record_route(
            mode=mode,
            function=function,
            final_backend="local",
            fallback_used=False,
            local_error=None,
            gemini_error=None,
            started_at=started_at,
        )
        return result

    if mode == "gemini_first":
        try:
            result = gemini_call()
        except LLMError as exc:
            gemini_error = exc
        else:
            _record_route(
                mode=mode,
                function=function,
                final_backend="gemini",
                fallback_used=False,
                local_error=None,
                gemini_error=None,
                started_at=started_at,
            )
            return result

        try:
            result = local_call()
        except LLMError as exc:
            local_error = exc
            _record_route(
                mode=mode,
                function=function,
                final_backend=None,
                fallback_used=True,
                local_error=local_error,
                gemini_error=gemini_error,
                started_at=started_at,
            )
            raise
        _record_route(
            mode=mode,
            function=function,
            final_backend="local",
            fallback_used=True,
            local_error=None,
            gemini_error=gemini_error,
            started_at=started_at,
        )
        return result

    if mode == "local_first":
        try:
            result = local_call()
        except LLMError as exc:
            local_error = exc
        else:
            _record_route(
                mode=mode,
                function=function,
                final_backend="local",
                fallback_used=False,
                local_error=None,
                gemini_error=None,
                started_at=started_at,
            )
            return result

        try:
            result = gemini_call()
        except LLMError as exc:
            gemini_error = exc
            _record_route(
                mode=mode,
                function=function,
                final_backend=None,
                fallback_used=True,
                local_error=local_error,
                gemini_error=gemini_error,
                started_at=started_at,
            )
            raise
        _record_route(
            mode=mode,
            function=function,
            final_backend="gemini",
            fallback_used=True,
            local_error=local_error,
            gemini_error=None,
            started_at=started_at,
        )
        return result

    raise LLMError(f"未知の HYBRID_MODE: {mode!r}（local_first / gemini_first / gemini_only / local_only のいずれか）")


def summarize_route_records(log_path: Path | None = None) -> dict[str, dict[str, int]]:
    """当日の LLM route telemetry を function 別に集計する。QUALITY_AUDIT は分母に含めない。"""
    path = log_path or _route_log_path()
    summary: dict[str, dict[str, int]] = {}
    if not path.exists():
        return summary

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        function = str(record.get("function") or "unknown")
        stats = summary.setdefault(
            function,
            {"total": 0, "local": 0, "gemini": 0, "fallback": 0, "errors": 0},
        )
        stats["total"] += 1
        backend = record.get("final_backend")
        if backend == "local":
            stats["local"] += 1
        elif backend == "gemini":
            stats["gemini"] += 1
        else:
            stats["errors"] += 1
        if record.get("fallback_used"):
            stats["fallback"] += 1
    return summary


def generate_event_extras(article_text: str, meta: dict) -> dict:
    """記事本文と meta から L2 拡張フィールドを生成。HYBRID_MODE に従い local / Gemini を切替。

    Args:
        article_text: 記事本文（MAX_BODY_CHARS でクランプ済の前提）
        meta: title / entity_name / category / vendor / entity_positioning の dict

    Returns:
        llm_gemini.generate_event_extras と同形の dict
        （summary / summary_points / rationale / score / importance / event_type）

    Raises:
        LLMError: 採用された経路（or 両経路）が失敗した場合
    """
    return _call_with_route(
        function="generate_event_extras",
        local_call=lambda: llm_local.generate_event_extras(article_text, meta),
        gemini_call=lambda: llm_gemini.generate_event_extras(article_text, meta),
    )


def regenerate_rationale(
    headline: str,
    summary: str,
    summary_points: list[str],
    importance_label: str,
    *,
    entity_context: dict | None = None,
) -> dict:
    """既存 event の headline/summary/summary_points から rationale 3 軸を再生成。

    境界 1 関数集約 ([[feedback_check_design_principles]] §2): apply 系スクリプトは
    llm_hybrid.regenerate_rationale を呼ぶだけで HYBRID_MODE 切替を意識しない
    (generate_event_extras / translate_headline_ja と同じ分岐ルール)。
    """
    args = (headline, summary, summary_points, importance_label)
    kw = {"entity_context": entity_context}
    return _call_with_route(
        function="regenerate_rationale",
        local_call=lambda: llm_local.regenerate_rationale(*args, **kw),
        gemini_call=lambda: llm_gemini.regenerate_rationale(*args, **kw),
    )


def translate_headline_ja(
    headline: str,
    *,
    entity_context: dict | None = None,
) -> str:
    """英語 headline を日本語に翻訳。HYBRID_MODE に従い local / Gemini 切替。

    境界 1 関数集約 ([[feedback_check_design_principles]] §2): collect_rss は
    llm_hybrid.translate_headline_ja を呼ぶだけで、フォールバック判断 / 例外整理を
    意識しない（generate_event_extras と同じ分岐ルール）。
    """
    return _call_with_route(
        function="translate_headline_ja",
        local_call=lambda: llm_local.translate_headline_ja(
            headline, entity_context=entity_context
        ),
        gemini_call=lambda: llm_gemini.translate_headline_ja(
            headline, entity_context=entity_context
        ),
    )


def translate_buzzpost_text_ja(text: str) -> str:
    """BuzzPost の英語本文を日本語へ翻訳する。HYBRID_MODE に従い local / Gemini を切替。

    X 風の表示では日本語をデフォルトにしつつ原文へ切替できるよう、収集側は
    text_original と翻訳後 text を分けて保持する。ここは翻訳境界だけを担う。
    """
    return _call_with_route(
        function="translate_buzzpost_text_ja",
        local_call=lambda: llm_local.translate_buzzpost_text_ja(text),
        gemini_call=lambda: llm_gemini.translate_buzzpost_text_ja(text),
    )
