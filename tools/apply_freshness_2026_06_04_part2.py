#!/usr/bin/env python3
"""鮮度レビュー Part 2 (残 15 entity) を data/entities.jsonl に反映する一回限りスクリプト。

handoff_2026-06-04_session_close_part5.md §2 中1 残 15 件 (agent 5 / infra 3 / media 2 /
physical 3 / policy 2) を対象。各 entity について:

- history 先頭 (now=true) 位置を **全件確認** してから新エントリを prepend (二重 prepend 防止)
- 既存 now=true を削除 / 新規 prepend エントリに now=true を付与
- snapshot_date を 2026-06-04 に更新
- 必要に応じて positioning / modules.future を修正 (EU AI Act 延期合意 / AgentKit Builder 廃止)

physical-intelligence は新リリース無しなので snapshot_date のみ更新。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
ENT_PATH = _ROOT / "data" / "entities.jsonl"
TODAY = "2026-06-04"


def _prepend_history(entity: dict, new_entries: list[dict]) -> None:
    """history 先頭に新エントリを prepend、既存 now=true を削除。

    new_entries は新しい順に並べた dict のリスト。先頭エントリに now=true を付与する。
    """
    hist = entity.setdefault("history", [])
    for h in hist:
        h.pop("now", None)
    if new_entries:
        new_entries[0]["now"] = True
    entity["history"] = new_entries + hist


def _patch_tesla_optimus(e: dict) -> None:
    _prepend_history(e, [
        {
            "when": "2026.04",
            "title": "Optimus V3 reveal 延期 + Fremont 量産ライン本格化準備",
            "note": "2026.04.22 Electrek 報道。Model S/X 生産跡地(早ければ 5 月終了)を Optimus 生産ラインに転用、7-8 月の本格生産開始を目指す。Musk は V3 公開を年後半に再延期し、初期生産率は『literally impossible to predict』と説明 (10,000 ユニーク部品 + 新ライン)。Fremont の初代年間生産能力は 100 万台規模、Gigafactory Texas は 2027 年夏に第 2 世代ライン稼働で年 1,000 万台体制を目指す",
            "source": "Electrek",
            "url": "https://electrek.co/2026/04/22/tesla-optimus-production-fremont-model-sx-line/",
        },
        {
            "when": "2026.01",
            "title": "Optimus Gen 3 pilot 生産開始 — 2026 年生産目標 5-10 万台",
            "note": "2026.01.21 Tesla が Fremont 工場で Optimus Gen 3 の pilot 生産を正式開始。2026 年の生産目標は 5 万〜10 万台。Gigafactory 内部利用から外販準備フェーズへ移行",
            "source": "Tesla / Electrek",
            "url": "https://electrek.co/2026/04/22/tesla-optimus-production-fremont-model-sx-line/",
        },
    ])


def _patch_runway(e: dict) -> None:
    _prepend_history(e, [
        {
            "when": "2025.12",
            "title": "Gen-4.5 公開 — Video Arena 1 位",
            "note": "2025.12.11 全有料プランに展開。Google・OpenAI の動画モデルを上回り Video Arena リーダーボード 1 位を獲得。物理現象・人間の動き・カメラワーク・因果関係の理解が大幅向上。同時にこれは『複数の主要リリースの第 1 弾』と公表",
            "source": "Runway",
            "url": "https://runwayml.com/research/introducing-runway-gen-4.5",
        },
    ])


def _patch_dify(e: dict) -> None:
    _prepend_history(e, [
        {
            "when": "2026.05",
            "title": "Dify 1.14.2 — MCP 統合 + Supervisor agent + hybrid RAG",
            "note": "MCP (Model Context Protocol) 対応で filesystem / GitHub / Slack / DB / ブラウザ等の外部ツールに接続。Agent loop に tool-call retry / 並列 tool 実行 / 複数サブエージェントを束ねる Supervisor agent モードを追加。RAG は dense+sparse の hybrid 検索 / chunk reranking / parent-document retrieval を内蔵。Gemini 3.x / Claude / GPT-4o mini / DeepSeek V3/R1 / Mistral Large / Ollama / LM Studio のローカルモデルにも対応",
            "source": "LangGenius / GitHub Releases",
            "url": "https://github.com/langgenius/dify/releases",
        },
    ])


def _patch_langgraph(e: dict) -> None:
    _prepend_history(e, [
        {
            "when": "2025.10",
            "title": "LangGraph 1.0 GA — durable agent framework の初メジャー版",
            "note": "durable state with automatic persistence を搭載しサーバ再起動後も agent が復旧、複数日にわたる承認プロセス・複数セッションをまたぐワークフローに対応。Standard JSON Schema 採用で Zod 4 / Valibot / ArkType と相互運用、ReducedValue (型安全な reducer) と UntrackedValue (永続化しないトランジェント状態) を追加",
            "source": "LangChain Changelog",
            "url": "https://changelog.langchain.com/announcements/langgraph-1-0-is-now-generally-available",
        },
    ])


def _patch_openclaw(e: dict) -> None:
    _prepend_history(e, [
        {
            "when": "2026.05",
            "title": "v2026.5 系列 — Skill Workshop + プラグイン外部化 + 信頼性大幅向上",
            "note": "2026.05.7 〜 5.30 beta 2 にかけて連続リリース。Skill Workshop 機能と plugin packaging を追加、Tokenjuice と GitHub Copilot ランタイムを @openclaw/tokenjuice / @openclaw/copilot として外部 npm プラグイン化。各種プロバイダ通信のタイマー / リトライ / OAuth/device-code ライフタイム / メディアダウンロードに bound を付与しハング防止。Telegram/WhatsApp/iMessage/Slack/Discord/Teams/Google Chat/Google Meet/iOS Talk の配信が安定化",
            "source": "OpenClaw / GitHub Releases",
            "url": "https://github.com/openclaw/openclaw/releases/tag/v2026.5.7",
        },
    ])


def _patch_cosmos(e: dict) -> None:
    # 既存の "2026.06 Cosmos 3 公開" を強化版で置き換え (先頭 1 件削除して新規 prepend)
    hist = e.get("history") or []
    # 既存先頭 (Cosmos 3 公開) を削除して詳細版で差し替え
    if hist and "Cosmos 3" in hist[0].get("title", ""):
        hist = hist[1:]
    e["history"] = hist
    _prepend_history(e, [
        {
            "when": "2026.06",
            "title": "Cosmos 3 公開 — mixture-of-transformers の世界基盤 omnimodel",
            "note": "2026.06.01 COMPUTEX 2026 で Jensen Huang が発表。reasoning transformer と expert generation transformer をペアにした mixture-of-transformers アーキテクチャで物体間相互作用 / 動作 / 時空間関係を理解してから動画と行動軌跡を生成する。high-physics の super と高速応答の nano の 2 モデル即時提供。Cosmos Coalition (Agile Robots / Black Forest Labs / Generalist / LTX / Runway / Skild AI) を立ち上げ open world model の発展を共同推進",
            "source": "NVIDIA Newsroom",
            "url": "https://nvidianews.nvidia.com/news/nvidia-launches-cosmos-3-the-open-frontier-foundation-model-for-physical-ai",
        },
    ])


def _patch_ironwood(e: dict) -> None:
    _prepend_history(e, [
        {
            "when": "2026.04",
            "title": "Broadcom 経由 Anthropic 大型契約 — 第 1 弾 400k TPU v7 Ironwood (約 $10B 相当)",
            "note": "Broadcom が Anthropic に対し 400,000 個の TPU v7 Ironwood (約 $10B 相当の完成ラック) を直接供給する大型契約を発表。Anthropic は 2026 年中に 100 万 TPU を超える展開、1GW 超の追加計算能力を確保する計画。Broadcom 開示では Google との広範な協業の一環として 2027 年から約 3.5GW の TPU ベース計算能力を Anthropic 向けに供給する。SemiAnalysis 推計では Ironwood の TCO は同等の NVIDIA GB200 比で約 30% 低い (内部利用なら -44%)",
            "source": "SemiAnalysis / Anthropic",
            "url": "https://newsletter.semianalysis.com/p/tpuv7-google-takes-a-swing-at-the",
        },
    ])


def _patch_vera_rubin(e: dict) -> None:
    _prepend_history(e, [
        {
            "when": "2026.06",
            "title": "Vera Rubin が full production 入り — agentic AI factory 向け",
            "note": "NVIDIA Vera Rubin プラットフォームが full production に到達し、AWS / Google Cloud / Microsoft / OCI に加え CoreWeave / Lambda / Nebius / Nscale が 2026 年下半期から Vera Rubin インスタンスを順次提供。Dell Technologies が世界初の Vera Rubin NVL72 ラックを CoreWeave に納入済。Microsoft は次世代 Fairwater AI superfactory で NVL72 を展開、OpenAI とのパートナーシップでは 2026 年下半期に第 1GW を Vera Rubin で稼働開始。Rubin CPX は 2026 年末提供開始予定",
            "source": "NVIDIA Newsroom",
            "url": "https://nvidianews.nvidia.com/news/vera-rubin-full-production-agentic-ai-factory",
        },
    ])


def _patch_flux(e: dict) -> None:
    _prepend_history(e, [
        {
            "when": "2026.03",
            "title": "FLUX.2 Speed Upgrade — 生成速度を 2 倍化 (品質低下なし)",
            "note": "2026.03.03 公表。Black Forest Labs が text-to-image と画像編集タスクで生成速度を 2 倍化、品質低下ゼロ。FLUX.2 Pro (32B / Mistral-3 24B VLM + rectified flow transformer / 最大 4MP) と Klein (Apache 2.0) を含むラインで段階展開",
            "source": "Black Forest Labs",
            "url": "https://bfl.ai/blog/flux-2",
        },
    ])


def _patch_figure(e: dict) -> None:
    _prepend_history(e, [
        {
            "when": "2026.05",
            "title": "Helix 02 ロボット 8 時間連続自律シフト + 寝室再構築デモ",
            "note": "2026.05.14 Figure AI が Helix 02 搭載の量産機による 8 時間連続自律シフト (週単位の宅配仕分けライブ配信) と人間 vs ロボット 10 時間競争で人間比 98.5% パフォーマンスを実現。同月 8 日には 2 台の Helix 02 ロボットが共有プランナーやメッセージング無しで partner の意図を動作から推定し、ドア開閉 / 衣服掛け / ベッドメイキングを含む寝室の完全再構築を 2 分以内に協調実行",
            "source": "Figure / TechTimes",
            "url": "https://www.techtimes.com/articles/316632/20260514/figure-ais-helix-02-robots-complete-full-8-hour-autonomous-shifts-humanoid-race-intensifies.htm",
        },
    ])


def _patch_eu_ai_act(e: dict) -> None:
    # positioning に延期合意の現状を反映
    e["positioning"] = "AI を包括的に規律する EU のリスクベース規制 (段階施行中、2026.05 の政治合意で高リスク AI 期限を 2027.12 に延期)"
    _prepend_history(e, [
        {
            "when": "2026.05",
            "title": "高リスク AI 期限延期で政治合意 — 2026.08 → 2027.12 へ",
            "note": "2026.05.07 EU 議会が AI Act 改定で政治合意。Annex III 高リスク AI 新規導入 / 大幅変更分は 16 か月延期、EU 製品安全規則対象に組み込まれる高リスク AI は 12 か月延期。実質的に高リスク AI 規制の本格運用が 2027.12 に後ろ倒し。AI Office / 加盟国の執行体制構築は継続し、最大 3% グローバル年商の罰金や市場撤回権限は 2026.08 に予定どおり発効",
            "source": "Latham & Watkins / Travers Smith",
            "url": "https://www.lw.com/en/insights/ai-act-update-eu-resolves-to-change-rules-and-extend-deadlines",
        },
    ])
    # modules.future の 2026.08 高リスク AI を延期注記で更新
    future = ((e.get("modules") or {}).get("future")) or []
    for f in future:
        if "2026.08" in f.get("title", "") or "高リスク AI" in f.get("title", ""):
            f["title"] = "2027.12 高リスク AI・透明性ルール本格執行 (2026.08 合意で延期)"
            f["note"] = "Annex III 高リスク AI 新規導入と組込み高リスク AI への執行を 2026.08 から 2027.12 に延期。透明性義務 (第50条) は予定どおり 2026.08 適用。AI Office は加盟国レベルでの執行体制構築を 2026.08 までに完了"
            f["url"] = "https://www.lw.com/en/insights/ai-act-update-eu-resolves-to-change-rules-and-extend-deadlines"


def _patch_japan_ai_act(e: dict) -> None:
    _prepend_history(e, [
        {
            "when": "2025.12",
            "title": "AI 基本計画閣議決定 + AI 統治体運用開始 + 適正利用ガイドライン",
            "note": "2025.12.23 AI 戦略本部が定めた AI 基本計画が閣議決定。同 12.19 には『人工知能関連技術の研究開発及び活用の適正性確保のためのガイドライン』を公表 (リスクベース・ステークホルダー関与・全ライフサイクル統治・俊敏な対応の 4 原則)。基本計画は (1) eldercare / 介護ロボへの応用 / (2) 国内 R&D・インフラ強化 / (3) ガイドラインによる信頼性確保 / (4) 国際統治への関与 の 4 本柱",
            "source": "内閣府 / HighlightingJapan",
            "url": "https://www.gov-online.go.jp/hlj/en/november_2025/november_2025-08.html",
        },
    ])


def _patch_devin(e: dict) -> None:
    # 既存先頭の "2026.06 Devin Desktop 公開" を Windsurf リブランド情報で強化
    hist = e.get("history") or []
    if hist and "Devin Desktop" in hist[0].get("title", ""):
        # 既存先頭を改良版で置き換え
        hist[0]["title"] = "Devin Desktop 公開 — Windsurf を完全リブランド + Devin Local (Rust) 投入"
        hist[0]["note"] = (
            "2026.06.02 Windsurf を Devin Desktop にリブランド (既存 Windsurf ユーザは OTA 更新)。"
            "Agent Command Center (Kanban で local + cloud agent を一括管理) を既定 surface に格上げ、"
            "agent 間のコンテキスト共有 Spaces を導入。ローカル agent は Rust でフルスクラッチ書き直しの "
            "Devin Local に置き換え (旧 Cascade は 2026.07.01 廃止)、トークン効率 30% 改善 + subagent サポート。"
            "Agent Client Protocol (ACP) をサポートし Codex / Claude Agent / OpenCode 等の互換 agent を Devin Desktop 内で実行可能"
        )
        hist[0]["source"] = "Cognition / Devin"
        hist[0]["url"] = "https://devin.ai/blog/windsurf-is-now-devin-desktop"


def _patch_agentkit(e: dict) -> None:
    # positioning に Builder 廃止を反映
    e["positioning"] = (
        "エージェントを構築・評価・本番投入まで一気通貫で支える OpenAI の統合ツールキット "
        "(Agent Builder は 2026.11.30 廃止予定、後継は新しいフロー編集体験へ移行)"
    )
    _prepend_history(e, [
        {
            "when": "2026.05",
            "title": "Agent Builder の 2026.11.30 廃止を公表 — 後継フローへ段階移行",
            "note": "Agent Builder は 2026.11.30 でシャットダウン予定。ChatKit と Evals は GA 継続、Connector Registry は API / Enterprise / Edu の Global Admin Console 対象顧客に順次提供中。Agent Builder で構築済みのワークフローは新しい後継フロー編集体験への移行が必要 (移行先と詳細仕様は順次公表)",
            "source": "OpenAI Developer Docs",
            "url": "https://developers.openai.com/api/docs/guides/agent-builder",
        },
    ])


# entity_id → patch 関数 のマッピング
PATCHERS = {
    "tesla-optimus": _patch_tesla_optimus,
    "runway": _patch_runway,
    "dify": _patch_dify,
    "langgraph": _patch_langgraph,
    "openclaw": _patch_openclaw,
    "cosmos": _patch_cosmos,
    "ironwood-tpu": _patch_ironwood,
    "vera-rubin": _patch_vera_rubin,
    "flux": _patch_flux,
    "figure": _patch_figure,
    "eu-ai-act": _patch_eu_ai_act,
    "japan-ai-act": _patch_japan_ai_act,
    "devin": _patch_devin,
    "agentkit": _patch_agentkit,
    # physical-intelligence は snapshot のみ更新 (新リリース無し)
    "physical-intelligence": lambda e: None,
}


def main() -> int:
    lines = ENT_PATH.read_text(encoding="utf-8").splitlines()
    out_lines: list[str] = []
    patched: set[str] = set()
    for ln in lines:
        if not ln.strip():
            out_lines.append(ln)
            continue
        e = json.loads(ln)
        eid = e.get("entity_id", "")
        if eid in PATCHERS:
            PATCHERS[eid](e)
            e["snapshot_date"] = TODAY
            patched.add(eid)
            print(f"  patched: {eid}")
        out_lines.append(json.dumps(e, ensure_ascii=False))
    missing = set(PATCHERS) - patched
    if missing:
        print(f"  ERROR: not found in entities.jsonl: {sorted(missing)}", file=sys.stderr)
        return 2
    ENT_PATH.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"\nApplied to {len(patched)} entities, written to {ENT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
