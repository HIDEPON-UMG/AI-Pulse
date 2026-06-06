"""ハイブリッド LLM ファサード: ローカル (Ollama Qwen3.6-35B-A3B) を通常パスに、失敗 / GPU 占有時のみ Gemini フォールバック。

なぜ重要か（意図）:
  Gemini API Free Tier は (a) RPD/RPM クォータ天井と (b) Google 学習データへの利用 という
  非コスト面のリスクがあり、AI-Pulse の本番抽出パスではローカル LLM を優先したい。一方で
  Ollama サーバ落ち / モデル未ロード / 他用途で GPU が占有されている時に止まると bot 全体が
  止まるため、Gemini を「安全網」として残す。

  境界を 1 関数 (generate_event_extras) に集約し、切替を HYBRID_MODE で可逆化する
  ([[feedback_check_design_principles]] §2「境界 1 箇所集約」)。class of bug は
  tests/test_llm_hybrid.py で locked-in（§4「契約テスト 1 件で不変条件」）。

  collect_rss は llm_hybrid.generate_event_extras を 1 回呼ぶだけで、フォールバック判断 /
  GPU プロービング / 例外整理を意識しない（呼出側は依然 LLMError 1 種だけ捕捉する）。

設計上の注意:
  - llm_local が `LLMError` を投げたら即フォールバック（hybrid 層では追加リトライしない。
    バックオフは llm_local 側で OLLAMA_MAX_RETRIES 回済んでいる）。
  - GPU 占有検出は nvidia-smi 1 ショット。smi が無い / 失敗した時は「占有でない」扱い
    （GPU 無し環境でも local を 1 度は試させ、失敗時のみ Gemini に流れるよう安全側に倒す）。
  - HYBRID_MODE=gemini_only は Ollama 全停止時の暫定回避用。
  - HYBRID_MODE=local_only は Gemini を絶対呼ばせたくない時の locked-in（テスト・実験用）。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import config  # noqa: E402
import llm_gemini  # noqa: E402
import llm_local  # noqa: E402
from _proc.run import quiet_run  # noqa: E402  # subprocess 直呼び ban の境界

# 呼出側は llm_hybrid.LLMError 1 種だけ捕捉すればよい（llm_gemini.LLMError と同一実体）。
LLMError = llm_gemini.LLMError


# silent fallback の稼働率を可視化するための provider counter。
# なぜ必要か（意図）:
#   local_first は「ローカル Ollama 失敗 → 即 Gemini」を黙って実行する設計のため、
#   外から「今日 Gemini が何回呼ばれたか」が見えない。Ollama サーバ落ち / GPU 占有が
#   続いていると「全件 Gemini で動いているのに成功扱い」になり、無料クォータ消費と
#   Google 学習データ提供が静かに進行する。本 counter で collect_rss 完了時に
#   「local N / Gemini M (X%)」を表示し、X が config.HYBRID_GEMINI_FALLBACK_WARN_RATIO
#   を超えたら警告する ([[feedback_check_design_principles]] §2 境界 1 箇所集約)。
#
# 設計:
#   - local / gemini は最終使用 provider (= 排他)。両者の和が「成功呼出回数」。
#   - gpu_busy_to_gemini / local_fail_to_gemini は gemini の内訳 (= gemini ≧ それらの和)。
#   - 両経路失敗で LLMError を投げた場合は counter を増分しない (= 失敗は別軸で集計)。
_STATS: dict[str, int] = {
    "local": 0,
    "gemini": 0,
    "gpu_busy_to_gemini": 0,
    "local_fail_to_gemini": 0,
}


def reset_stats() -> None:
    """カウンタを全てゼロに戻す。バッチ開始時に collect_rss が呼ぶ。"""
    for k in _STATS:
        _STATS[k] = 0


def get_stats() -> dict[str, int]:
    """カウンタのスナップショットを返す (呼出側からの破壊的変更を避けるため copy)。"""
    return dict(_STATS)


def _record(provider: str, *, reason: str | None = None) -> None:
    """成功した呼出を 1 件記録する。

    provider: "local" or "gemini"
    reason  : "gpu_busy" or "local_fail" (gemini 経路の内訳。local 時は None)
    """
    _STATS[provider] += 1
    if reason:
        _STATS[f"{reason}_to_gemini"] += 1


def _query_gpu_memory_mb() -> int | None:
    """nvidia-smi で 1 ショット問い合わせて GPU メモリ使用量 (MB) を返す。

    返り値: 使用 MB (int) / 取得失敗時は None。
    nvidia-smi が PATH に無い・実行失敗・パース失敗は None で「占有判定なし」とする
    （= local を 1 度は試させる安全側）。

    Windows 黒窓は quiet_run (tools/_proc/run.py) 経由で CREATE_NO_WINDOW 強制済。
    """
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    try:
        proc = quiet_run(
            [smi, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            timeout=5,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip().splitlines()
    if not out:
        return None
    try:
        return int(out[0].strip())
    except ValueError:
        return None


def _gpu_busy(
    *,
    threshold_mb: int | None = None,
    probe: Callable[[], int | None] | None = None,
) -> bool:
    """GPU が他用途で占有されているか判定。閾値超なら True を返す。

    Args:
        threshold_mb: 占有判定の閾値 (MB)。省略時は config.HYBRID_GPU_THRESHOLD_FB_MB。
        probe: テスト用の MB 取得関数差し替え。None なら nvidia-smi を直接叩く。

    nvidia-smi 未インストール / 取得失敗 (probe が None を返す) は「占有でない」扱い:
        GPU 無し環境でも local を 1 度は試して、Ollama 接続失敗で Gemini に落ちる経路を保つ。
    """
    threshold = threshold_mb if threshold_mb is not None else config.HYBRID_GPU_THRESHOLD_FB_MB
    used = probe() if probe is not None else _query_gpu_memory_mb()
    if used is None:
        return False
    return used >= threshold


def generate_event_extras(
    article_text: str,
    meta: dict,
    *,
    gpu_probe: Callable[[], int | None] | None = None,
) -> dict:
    """記事本文と meta から L2 拡張フィールドを生成。HYBRID_MODE に従い local / Gemini を切替。

    Args:
        article_text: 記事本文（MAX_BODY_CHARS でクランプ済の前提）
        meta: title / entity_name / category / vendor / entity_positioning の dict
        gpu_probe: テスト用の GPU メモリ取得関数差し替え（本番は None で nvidia-smi）

    Returns:
        llm_gemini.generate_event_extras と同形の dict
        （summary / summary_points / rationale / score / importance / event_type）

    Raises:
        LLMError: 採用された経路（or 両経路）が失敗した場合
    """
    mode = config.HYBRID_MODE

    if mode == "gemini_only":
        result = llm_gemini.generate_event_extras(article_text, meta)
        _record("gemini")
        return result

    if mode == "local_only":
        result = llm_local.generate_event_extras(article_text, meta)
        _record("local")
        return result

    if mode == "gemini_first":
        # クォータ温存より「Gemini で品質保証」を優先したい比較・A/B 用。
        try:
            result = llm_gemini.generate_event_extras(article_text, meta)
            _record("gemini")
            return result
        except LLMError:
            result = llm_local.generate_event_extras(article_text, meta)
            _record("local")
            return result

    if mode == "local_first":
        # 既定。GPU 占有時は local を試さず即 Gemini に流し、待ち時間 / VRAM 競合を避ける。
        if _gpu_busy(probe=gpu_probe):
            result = llm_gemini.generate_event_extras(article_text, meta)
            _record("gemini", reason="gpu_busy")
            return result
        try:
            result = llm_local.generate_event_extras(article_text, meta)
            _record("local")
            return result
        except LLMError:
            result = llm_gemini.generate_event_extras(article_text, meta)
            _record("gemini", reason="local_fail")
            return result

    raise LLMError(f"未知の HYBRID_MODE: {mode!r}（local_first / gemini_first / gemini_only / local_only のいずれか）")


def regenerate_rationale(
    headline: str,
    summary: str,
    summary_points: list[str],
    importance_label: str,
    *,
    entity_context: dict | None = None,
    gpu_probe: Callable[[], int | None] | None = None,
) -> dict:
    """既存 event の headline/summary/summary_points から rationale 3 軸を再生成。

    境界 1 関数集約 ([[feedback_check_design_principles]] §2): apply 系スクリプトは
    llm_hybrid.regenerate_rationale を呼ぶだけで HYBRID_MODE 切替を意識しない
    (generate_event_extras / translate_headline_ja と同じ分岐ルール)。
    """
    mode = config.HYBRID_MODE
    args = (headline, summary, summary_points, importance_label)
    kw = {"entity_context": entity_context}

    if mode == "gemini_only":
        result = llm_gemini.regenerate_rationale(*args, **kw)
        _record("gemini")
        return result

    if mode == "local_only":
        result = llm_local.regenerate_rationale(*args, **kw)
        _record("local")
        return result

    if mode == "gemini_first":
        try:
            result = llm_gemini.regenerate_rationale(*args, **kw)
            _record("gemini")
            return result
        except LLMError:
            result = llm_local.regenerate_rationale(*args, **kw)
            _record("local")
            return result

    if mode == "local_first":
        if _gpu_busy(probe=gpu_probe):
            result = llm_gemini.regenerate_rationale(*args, **kw)
            _record("gemini", reason="gpu_busy")
            return result
        try:
            result = llm_local.regenerate_rationale(*args, **kw)
            _record("local")
            return result
        except LLMError:
            result = llm_gemini.regenerate_rationale(*args, **kw)
            _record("gemini", reason="local_fail")
            return result

    raise LLMError(f"未知の HYBRID_MODE: {mode!r}")


def translate_headline_ja(
    headline: str,
    *,
    entity_context: dict | None = None,
    gpu_probe: Callable[[], int | None] | None = None,
) -> str:
    """英語 headline を日本語に翻訳。HYBRID_MODE に従い local / Gemini 切替。

    境界 1 関数集約 ([[feedback_check_design_principles]] §2): collect_rss は
    llm_hybrid.translate_headline_ja を呼ぶだけで、フォールバック判断 / GPU プロービング /
    例外整理を意識しない（generate_event_extras と同じ分岐ルール）。
    """
    mode = config.HYBRID_MODE

    if mode == "gemini_only":
        result = llm_gemini.translate_headline_ja(headline, entity_context=entity_context)
        _record("gemini")
        return result

    if mode == "local_only":
        result = llm_local.translate_headline_ja(headline, entity_context=entity_context)
        _record("local")
        return result

    if mode == "gemini_first":
        try:
            result = llm_gemini.translate_headline_ja(
                headline, entity_context=entity_context
            )
            _record("gemini")
            return result
        except LLMError:
            result = llm_local.translate_headline_ja(
                headline, entity_context=entity_context
            )
            _record("local")
            return result

    if mode == "local_first":
        if _gpu_busy(probe=gpu_probe):
            result = llm_gemini.translate_headline_ja(
                headline, entity_context=entity_context
            )
            _record("gemini", reason="gpu_busy")
            return result
        try:
            result = llm_local.translate_headline_ja(
                headline, entity_context=entity_context
            )
            _record("local")
            return result
        except LLMError:
            result = llm_gemini.translate_headline_ja(
                headline, entity_context=entity_context
            )
            _record("gemini", reason="local_fail")
            return result

    raise LLMError(f"未知の HYBRID_MODE: {mode!r}")
