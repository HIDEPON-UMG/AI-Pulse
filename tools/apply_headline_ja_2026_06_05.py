#!/usr/bin/env python3
"""英語タイトル 82 件に Claude 直接翻訳の `headline_ja` を付与する一回限りスクリプト。

events.jsonl のうち ASCII 比率 0.85+ の英語見出しを対象。日本語見出しは触らない。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
EV_PATH = _ROOT / "data" / "events.jsonl"

TRANS: dict[str, str] = {
    "2026-06-03-claudeop-gem01": "Claude Opus 4.8 と 4.7 を 10 ラウンドの正直さテストで比較してみた",
    "2026-06-02-claudeop-gem03": "Microsoft、エンジニアに Anthropic Claude の使用停止を指示 — Claude Code ライセンス解約へ",
    "2026-06-02-claudeop-gem04": "Anthropic、Glasswing 拡張で Mythos クラス Claude モデルの公開リリースを約束",
    "2026-06-02-claudeop-gem05": "Claude AI 障害発生 — Anthropic が障害発生を認める",
    "2026-05-29-devin-gem03": "Cognition の Scott Wu「AI コーディングエージェントは人間を置き換えるべきでない」",
    "2026-05-29-devin-gem04": "Fiserv、コアバンキング刷新を加速するため Devin AI を採用",
    "2026-04-07-cursor-gem01": "Cursor AI 評価額 600 億ドル到達 — Anysphere の収益 20 億ドルが急伸",
    "2026-05-19-cursor-gem02": "37 位: Cursor (ランキング掲載)",
    "2026-04-29-cursor-gem03": "独占報道: 米下院委員会、Cursor 親会社と Airbnb を中国 AI 関連で調査",
    "2026-03-11-cursor-gem04": "Cursor 追加資金調達を検討 — コーディング企業の見通しを巡る議論激化",
    "2026-04-22-cursor-gem05": "SpaceX、AI コーディングツール Cursor を年内に 600 億ドルで買収可能と表明",
    "2026-06-02-flux-gem01": "これぞ映画? Martin Scorsese、次作の絵コンテ作成に AI を活用",
    "2026-06-03-flux-gem02": "Martin Scorsese、新作 DiCaprio 映画で Black Forest Labs に AI アドバイザー就任",
    "2026-06-02-flux-gem04": "Martin Scorsese、ハリウッドの AI 未来に対する過去最大の支持を表明",
    "2026-06-03-physical-gem01": "HKUST と CalmCar、フィジカル AI イノベーションセンター設立 — フィジカル知能の新時代へ",
    "2026-06-02-physical-gem02": "Andrew Kang: ヒューマノイドは 3-5 年で日常生活に統合され市場は数兆ドル規模に — フィジカル知能がロボティクスに革命",
    "2026-04-29-physical-gem04": "フィジカル知能でロボティクスを再考する",
    "2026-04-16-physical-gem05": "Physical Intelligence、新ロボット脳が未学習タスクも実行可能と発表 — 注目のロボティクス新興",
    "2026-05-28-devin-gem01": "Fiserv と Cognition が提携 — 銀行業務技術の現代化とクライアントへの新機能提供を加速",
    "2026-06-01-devin-gem02": "Fiserv (FISV) と Cognition、コアバンキング刷新で Devin AI を展開",
    "2026-04-23-devin-gem05": "Cognition (Devin 開発元)、評価額 250 億ドルで数億ドル調達交渉中",
    "2026-06-01-verarubi-gem01": "NVIDIA、エージェント向け CPU『Vera』を発表",
    "2026-06-01-verarubi-gem02": "NVIDIA Vera Rubin、世界のエージェント AI ファクトリーを支える本格生産フェーズに移行",
    "2026-06-01-verarubi-gem03": "NVIDIA、次世代 AI ファクトリー基盤 Vera Rubin の生産を増強",
    "2026-06-01-verarubi-gem04": "NVIDIA、Vera Rubin の本格生産を確認 — 台湾 150 社サプライヤが量産を支える",
    "2026-06-01-verarubi-gem05": "NVIDIA「実用的な AI が到来した」— Vera Rubin 本格生産入りで宣言",
    "2026-06-03-euaiact-gem01": "欧州の技術主権の強化に向けて",
    "2026-06-03-euaiact-gem02": "AIGG EU 基調講演で EU AI 主権が焦点に",
    "2026-06-03-euaiact-gem04": "EU AI・著作権規則の改訂は 6,000 億ユーロをリスクに — 新調査が警告",
    "2026-05-24-figure-gem01": "ヒューマノイドロボット、荷物仕分けテストで連続稼働",
    "2026-05-20-figure-gem02": "Figure AI のヒューマノイドが荷物を扱う動画にネット中が釘付け",
    "2026-05-26-figure-gem03": "Figure、Catalyst Brands と契約 — ヒューマノイド運用拡大へ",
    "2026-05-26-figure-gem04": "Catalyst Brands、ヒューマノイド自動化のため Figure AI を採用",
    "2026-05-19-figure-gem05": "Figure AI、自社ロボットとインターンで荷物仕分け対決 — 敗者は誰か",
    "2025-10-06-agentkit-gem01": "AgentKit を発表",
    "2025-10-06-agentkit-gem02": "OpenAI、開発者の AI エージェント構築・出荷を支援する AgentKit を公開",
    "2025-10-07-agentkit-gem04": "OpenAI、AgentKit のチャットインターフェイスを公開",
    "2025-10-06-agentkit-gem05": "OpenAI、ノーコード Agent Builder を公開",
    "2026-05-30-ironwood-gem01": "Google TPU v8 対 NVIDIA — 推論が AI 市場を塗り替える構造",
    "2025-11-25-ironwood-gem02": "最新 TPU『Ironwood』について知るべき 3 つのポイント",
    "2025-11-06-ironwood-gem03": "Google、最強 AI チップを展開 — カスタムシリコンで NVIDIA に挑戦",
    "2026-04-22-ironwood-gem04": "Google、推論向け TPU 8i と訓練向け TPU 8t を発表",
    "2026-04-14-japanaia-gem01": "日本初の AI 法が成立 — 研究開発推進が焦点、罰則規定なし",
    "2026-02-16-japanaia-gem02": "総選挙後の日本: AI 政策・規制・運用面のアップデート",
    "2026-03-24-japanaia-gem03": "韓国の新 AI 基本法 — 特徴と意義",
    "2026-02-25-japanaia-gem05": "台湾の AI 基本法はアジアのモデルになり得る",
    "2026-03-04-qwen-gem03": "Qwen 技術リード辞任の舞台裏",
    "2026-06-02-qwen-gem04": "Alibaba、Claude Opus 4.6 相当の AI モデル『Qwen3.7-Plus』を発表",
    "2026-05-18-qwen-gem05": "中国、ある重要分野の AI で米国を凌駕",
    "2026-06-03-deepseek-gem01": "DeepSeek、初の資金調達ラウンドで 70 億ドル獲得予定 — 関係者",
    "2026-06-03-deepseek-gem02": "トランプ大統領、待望の縮小版 AI 大統領令の詳細",
    "2026-06-03-deepseek-gem04": "中国 AI ラボ DeepSeek、60 億ユーロ調達予定",
    "2026-06-03-deepseek-gem05": "DeepSeek、初の資金調達ラウンドで 100 億ドル調達へ",
    "2026-06-02-gemini-gem01": "Gemini Spark、これまでで最も印象的かつ恐ろしい AI 体験",
    "2026-06-01-gemini-gem02": "Google I/O 2026 を Gemini で構築した方法",
    "2026-06-03-gemini-gem04": "AI の性能向上が暴く空虚な約束",
    "2026-06-03-gemini-gem05": "悪意ある通知が Google Gemini ユーザーを欺く可能性",
    "2025-11-14-windsurf-gem01": "Cursor 対 Windsurf (Codeium): 機能と価格の比較ガイド",
    "2025-12-22-windsurf-gem02": "2025 年ベスト: OpenAI、Windsurf を 30 億ドルで買収",
    "2025-07-11-windsurf-gem03": "OpenAI と AI コーディング新興 Windsurf の 30 億ドル契約破綻 — Google がライセンス契約で割り込む",
    "2025-03-23-windsurf-gem04": "Windsurf/Codeium が 10 億ドル企業と勝てる営業組織を築いた方法",
    "2025-07-14-windsurf-gem05": "Google、24 億ドル契約で Windsurf 経営陣を獲得 — OpenAI 最大の買収案件を頓挫させる",
    "2026-06-01-cosmos-gem01": "NVIDIA Cosmos 3 でフィジカル AI 推論・世界・行動モデルを開発する",
    "2026-06-01-cosmos-gem03": "NVIDIA、フィジカル AI 向けオープン基盤モデル Cosmos 3 を公開",
    "2026-06-02-cosmos-gem04": "NVIDIA Cosmos 3 とオープンエージェントツール — フィジカル AI は研究室を飛び出すか",
    "2026-06-03-cosmos-gem05": "NVIDIA、Cosmos 3 公開 — フィジカル推論・世界生成・行動生成を統合する 2 タワー MoT 基盤モデル",
    "2026-06-01-llama-gem01": "Osmo、嗅覚をデジタル化 — AWS 上の Meta Llama で AI コストを 200 分の 1 に",
    "2026-06-02-llama-gem02": "Meta AI — オープンソースエコシステムがクラウドを制する構造",
    "2026-04-30-llama-gem03": "Meta、オープンソース Llama を断念して独自 Muse Spark へ転向",
    "2026-04-13-llama-gem05": "Muse Spark — Llama 失望後に Meta が再構築した AI スタック",
    "2024-02-20-dify-gem01": "Edge 371 — Skeleton of Thoughts による 2 段階 LLM 推論",
    "2025-03-22-dify-gem02": "2024 年最も注目された OSS スタートアップ 20 選",
    "2026-05-26-langgrap-gem01": "Amazon Bedrock AgentCore で AWS 上にスケーラブルなサーバーレス LangGraph マルチエージェントを構築",
    "2026-03-27-langgrap-gem02": "LangChain・LangGraph の脆弱性、広く使われる AI フレームワークでファイル・機密・DB を露出",
    "2025-12-15-langgrap-gem03": "本番環境を LangChain 1.0 にアップグレードして学んだ教訓",
    "2026-05-08-langgrap-gem04": "watsonx Orchestrate で LangGraph エージェントを本番運用へ",
    "2026-01-29-langgrap-gem05": "RAG フレームワーク比較 — LangChain 対 LangGraph 対 LlamaIndex",
    "2026-06-03-runway-gem01": "Rent the Runway、Q1 売上急増を背景に経営陣を刷新",
    "2026-06-03-runway-gem02": "Springer 市営空港、電気設備改修完了 — 滑走路改良も計画",
    "2026-06-01-teslaopt-gem02": "Tesla Optimus と Musk に新たな脅威 — OpenAI ロボティクス参入",
    "2026-06-01-teslaopt-gem04": "Tesla Optimus に新脅威 — OpenAI ロボティクス事業参入",
    "2026-05-27-teslaopt-gem05": "Tesla、Optimus 専用工場建設をギガテキサスで正式着手",
}


def main() -> int:
    lines = EV_PATH.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    applied = set()
    for ln in lines:
        if not ln.strip():
            out.append(ln)
            continue
        ev = json.loads(ln)
        eid = ev.get("event_id", "")
        if eid in TRANS:
            ev["headline_ja"] = TRANS[eid]
            applied.add(eid)
        out.append(json.dumps(ev, ensure_ascii=False))
    missing = set(TRANS) - applied
    if missing:
        print(f"  WARN: event_id not found in events.jsonl: {sorted(missing)}", file=sys.stderr)
    EV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Applied headline_ja to {len(applied)}/{len(TRANS)} events")
    return 0


if __name__ == "__main__":
    sys.exit(main())
