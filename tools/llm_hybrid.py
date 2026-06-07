"""ハイブリッド LLM ファサード: ローカル (Ollama Qwen3.6-35B-A3B) を通常パスに、失敗時のみ Gemini フォールバック。

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

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import config  # noqa: E402
import llm_gemini  # noqa: E402
import llm_local  # noqa: E402

# 呼出側は llm_hybrid.LLMError 1 種だけ捕捉すればよい（llm_gemini.LLMError と同一実体）。
LLMError = llm_gemini.LLMError


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
    mode = config.HYBRID_MODE

    if mode == "gemini_only":
        return llm_gemini.generate_event_extras(article_text, meta)

    if mode == "local_only":
        return llm_local.generate_event_extras(article_text, meta)

    if mode == "gemini_first":
        # クォータ温存より「Gemini で品質保証」を優先したい比較・A/B 用。
        try:
            return llm_gemini.generate_event_extras(article_text, meta)
        except LLMError:
            return llm_local.generate_event_extras(article_text, meta)

    if mode == "local_first":
        # 既定。常に local を 1 度試し、Ollama が LLMError を返した時のみ Gemini に落とす。
        try:
            return llm_local.generate_event_extras(article_text, meta)
        except LLMError:
            return llm_gemini.generate_event_extras(article_text, meta)

    raise LLMError(f"未知の HYBRID_MODE: {mode!r}（local_first / gemini_first / gemini_only / local_only のいずれか）")


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
    mode = config.HYBRID_MODE
    args = (headline, summary, summary_points, importance_label)
    kw = {"entity_context": entity_context}

    if mode == "gemini_only":
        return llm_gemini.regenerate_rationale(*args, **kw)

    if mode == "local_only":
        return llm_local.regenerate_rationale(*args, **kw)

    if mode == "gemini_first":
        try:
            return llm_gemini.regenerate_rationale(*args, **kw)
        except LLMError:
            return llm_local.regenerate_rationale(*args, **kw)

    if mode == "local_first":
        try:
            return llm_local.regenerate_rationale(*args, **kw)
        except LLMError:
            return llm_gemini.regenerate_rationale(*args, **kw)

    raise LLMError(f"未知の HYBRID_MODE: {mode!r}")


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
    mode = config.HYBRID_MODE

    if mode == "gemini_only":
        return llm_gemini.translate_headline_ja(headline, entity_context=entity_context)

    if mode == "local_only":
        return llm_local.translate_headline_ja(headline, entity_context=entity_context)

    if mode == "gemini_first":
        try:
            return llm_gemini.translate_headline_ja(
                headline, entity_context=entity_context
            )
        except LLMError:
            return llm_local.translate_headline_ja(
                headline, entity_context=entity_context
            )

    if mode == "local_first":
        try:
            return llm_local.translate_headline_ja(
                headline, entity_context=entity_context
            )
        except LLMError:
            return llm_gemini.translate_headline_ja(
                headline, entity_context=entity_context
            )

    raise LLMError(f"未知の HYBRID_MODE: {mode!r}")
