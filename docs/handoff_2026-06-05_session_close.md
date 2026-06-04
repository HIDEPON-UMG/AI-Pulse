# 次セッション引継ぎ — 2026-06-05 セッションクローズ

作成: 2026-06-05 (本セッション末)
直近 push 済: `f7cc1e4` (= origin/master HEAD、本セッションで master へ push 済)
末尾追加 (未コミット): スコア⇔画像の横隙間詰め (列 160→100 / gap 24→8)

前 handoff 系列 (Part 1-5、すべて 2026-06-04 起票):
- [docs/handoff_2026-06-04_session_close.md](handoff_2026-06-04_session_close.md) (Part 1)
- [docs/handoff_2026-06-04_session_close_part2.md](handoff_2026-06-04_session_close_part2.md)
- [docs/handoff_2026-06-04_session_close_part3.md](handoff_2026-06-04_session_close_part3.md)
- [docs/handoff_2026-06-04_session_close_part4.md](handoff_2026-06-04_session_close_part4.md)
- [docs/handoff_2026-06-04_session_close_part5.md](handoff_2026-06-04_session_close_part5.md)

> **Part 5 → 本セッションの差分**: Part 5 §2 で残 15 件 (agent 5 / infra 3 / media 2 / physical 3 / policy 2) と挙げていた中1 鮮度レビューを **全件完了**。途中で UI 拡大要望 (サムネ 1.5x / カルテボタン 1.5x / スコア 2x) と「タグフィルターが効いてない」報告が割り込み、両方を同 commit に束ねた。最後にスコアと画像の横隙間詰めも追加要望。

---

## 1. 本セッションで実施した作業

### 1.1 鮮度レビュー Part 2 (中1 残 15 件)

handoff Part 5 §2 中1 残タスクの全件完了。各 entity の history 先頭 + `now=true` 位置を **事前に全件確認** したうえで prepend し、Part 5 で起きた二重 prepend 事故 (history 末尾 3 件だけ見る) を構造的に回避。

| entity | 主な追加・変更 | 新規 URL |
|---|---|---|
| tesla-optimus | 2026.04 V3 reveal 延期 + Fremont 量産準備 / 2026.01 Optimus Gen 3 pilot 生産開始 (5-10万台目標) | `electrek.co/2026/04/22/...` |
| runway | 2025.12 Gen-4.5 公開 (Video Arena No.1) | `runwayml.com/research/introducing-runway-gen-4.5` |
| dify | 2026.05 v1.14.2 + MCP 統合 + Supervisor agent + hybrid RAG | `github.com/langgenius/dify/releases` |
| langgraph | 2025.10 LangGraph 1.0 GA — durable state | `changelog.langchain.com/announcements/langgraph-1-0-is-now-generally-available` |
| openclaw | 2026.05 v2026.5 系列 + Skill Workshop + plugin packaging + Tokenjuice/Copilot 外部化 | `github.com/openclaw/openclaw/releases/tag/v2026.5.7` |
| cosmos | 既存 Cosmos 3 公開を mixture-of-transformers / super+nano / Cosmos Coalition 詳細で強化 | `nvidianews.nvidia.com/news/nvidia-launches-cosmos-3-...` |
| ironwood-tpu | 2026.04 Broadcom $10B (400k TPU v7 Ironwood 第一弾) + Anthropic 1M TPU 構想 + 2027 3.5GW 拡張 | `newsletter.semianalysis.com/p/tpuv7-google-takes-a-swing-at-the` |
| vera-rubin | 2026.06 Rubin full production 入り + Dell-CoreWeave NVL72 初出荷 + 2026 H2 提供開始 | `nvidianews.nvidia.com/news/vera-rubin-full-production-agentic-ai-factory` |
| flux | 2026.03 FLUX.2 Speed Upgrade (2x 速度・品質低下なし) | `bfl.ai/blog/flux-2` |
| figure | 2026.05 Helix 02 で 8h 連続自律シフト + 寝室再構築 (2 台無メッセージング協調) | `techtimes.com/articles/316632/20260514/...` |
| eu-ai-act | **重要**: 2026.05.07 高リスク AI 期限 2026.08→2027.12 延期合意 + positioning 修正 + modules.future 更新 | `lw.com/en/insights/ai-act-update-eu-resolves...` |
| japan-ai-act | 2025.12.23 AI 基本計画閣議決定 + 12.19 適正利用ガイドライン公表 | `gov-online.go.jp/hlj/en/november_2025/november_2025-08.html` |
| devin | 既存 Devin Desktop を Windsurf リブランド情報で強化 (Devin Local Rust 30% 効率改善・ACP プロトコル) | `devin.ai/blog/windsurf-is-now-devin-desktop` |
| agentkit | **重要**: 2026.05 Agent Builder 2026.11.30 廃止予告 + positioning 修正 | `developers.openai.com/api/docs/guides/agent-builder` |
| physical-intelligence | 新リリースなし → snapshot_date のみ更新 | — |

検証実測値:
- **pytest 54 PASS** (38.33s)
- **audit_urls --gate: 159/159 OK** (Part 5 末 146 → +13 = 159)
- **新規 22 URL 全てが 3 段プローブで実機 200 OK**

### 1.2 トップフィード UI 拡大 (ユーザー追加要望)

ユーザーが現物スクショで「サムネとカルテボタンが小さい」「スコアも 2 倍でいい」「スコアと画像の隙間が無駄」と段階的に指示。1 commit (`f7cc1e4`) に束ねる方針で全 3 件実装。

| 要素 | 修正前 | 修正後 |
|---|---|---|
| 親 grid (PC) | `80px 200px 1fr` gap 24 | `100px 300px 1fr` gap 8 (= 列 80→100、サムネ 1.5x、横 gap 24→8) |
| 親 grid (タブ 601-860) | `64px 160px 1fr` | `80px 240px 1fr` |
| 親 grid (スマホ <600) | `64px 1fr` | `96px 1fr` (score 列 1.5x) |
| `.story .score .num` | 28px (スマホ 22px) | 56px (スマホ 36px) |
| `.story .score .lbl` / `.date` | 9 / 11 / 10px | 13 / 16 / 14px |
| `.story .karte-chip` | 15px / padding 6 11 | 22px / padding 9 17 |
| `.story .karte-chips` gap | 6px | 9px |

最後の「スコアと画像隙間」は本セッション末尾の追加要望で、`grid-template-columns` の score 列を 160→100px に詰めて gap も 24→8px に縮小。これは push 済 `f7cc1e4` の **後** の未コミット差分。

### 1.3 [重大] タグフィルターバグ修正

ユーザー報告「タグフィルター効いてない」を当初は「コード上は正常動作」と返したが、現物スクショで「『画像・動画・音声生成』chip が pressed=false なのに media story が表示されている」を確認。chrome-devtools MCP で実機検証したところ:

```
hidden: true, computedDisplay: "grid", visibleHeight: 573  ← バグ
```

真因: `.story { display: grid }` が UA stylesheet の `[hidden] { display: none }` を **CSS specificity で打ち負かしていた**。`feedback_web_ui_e2e_test` で警告されている古典的な class of bugs。私の最初の検証は `el.hidden` プロパティだけ見ていて視覚状態 (`computedDisplay`) を確認していなかった。

恒久封じ込め: `feedback_check_design_principles` 段位 2 (境界 1 箇所集約) で `static/theme.css` の冒頭に追加:

```css
[hidden] { display: none !important; }
```

修正後の実機検証:
```
hidden: true, computedDisplay: "none", visibleHeight: 0  ← クリア
```

AI-Pulse 全画面の `[hidden]` を物理的に保証する境界 1 箇所集約。今後 `.story` 以外でも `display: grid`/`flex` 指定が増えても hidden は常に勝つ。

### 1.4 PWA SW v7 → v8 bump

safe-commit ゲート 6 (PWA SW 同期) で「アセット変更 + SW 未 bump = コミット拒否」が発火し、`static/sw.js` の `CACHE = "aipulse-v7"` を `v8` に更新。既存 PWA インストールにキャッシュ無効化が確実に伝わる。

### 1.5 commit と push

```
f7cc1e4 鮮度レビュー Part 2 (残 15 entity) + index トップ UI 拡大 + タグフィルター恒久バグ修正
       8b679fe..f7cc1e4  master -> master   (HIDEPON-UMG/AI-Pulse)
```

`f7cc1e4` に含む 6 ファイル: `data/entities.jsonl` / `templates/index.html.j2` / `static/theme.css` / `static/sw.js` / `tools/apply_freshness_2026_06_04_part2.py` / `tools/check_freshness_urls_part6.py`

safe-commit 全ゲート通過:
- ゲート 1 (個人情報): クリア (差分・新規ファイルとも検出 0)
- ゲート 2 (セキュリティ): 軽量チェックでクリア (SQL inj / XSS / path traversal / cmd inj / DoS / auth どれも該当なし)
- ゲート 3 (機密情報質問): 該当なし
- ゲート 4 (DESIGN.md): errors=0 / warnings=30 (既存 tier-2 / tier-3 など未参照、本コミット非関連)
- ゲート 4' (HTML 仕様書): 該当なし
- ゲート 5 (実機エントリ): smoke 未整備 → スキップ (AI-Pulse は SSG / scripts/smoke_pages.py 無し)
- ゲート 6 (PWA SW 同期): v7→v8 bump 済でクリア

---

## 2. 残タスク (Part 5 受領 − 本セッション done + 派生)

`feedback_handoff_inventory_diff_closeout` に従い、作業記憶でなく受領全量 (Part 5 §2 + 本セッション派生) から差分で列挙。

### 中 (本セッション末尾の未コミット分)

1. **スコア⇔画像隙間詰めの commit & push** (本セッション末尾派生)
   - `templates/index.html.j2`: 親 grid 列 `160px 300px 1fr` → `100px 300px 1fr`、横 gap `var(--s-24)` → `var(--s-8)`、タブレット 128→80
   - 視覚確認済 (chrome-devtools MCP スクショ): スコア「55」と画像が隣接
   - **GO 待ち** (commit + push 単独で 1 件)

### 中 (Part 5 から継続)

2. **モバイル 390px 真幅 E2E** (Part 5 中2 継承)
   - chrome-devtools MCP の `resize` は ~501px 最小幅クランプ → `emulate` ツールで真幅検証
   - 本セッションでスコア列 64→96、num 22→36 にスマホ調整しているが実機未検証

### 低

3. **未追跡ファイル整理判断** (Part 5 低4 継承、本セッションでは触らず)
   - Part 4 継続: `M tools/config.py` (Ollama qwen3 backend 切替)
   - Part 4 継続: `?? docs/eval/2026-06-04_blind_judge.{md,raw.json}` / `_fabrication_fix.{md,raw.json}` / `_local_llm_investigation.{md,html}` / `_qwen3_vs_gemini.md`
   - Part 4 継続: `?? docs/handoff_2026-06-04_karte_polish_pending.md`
   - Part 4 継続: `?? docs/handoff_2026-06-04_session_close.md` / `_part2.md` / `_part3.md` / `_part5.md` (Part 4 だけは 8b679fe で push 済)
   - Part 4 継続: `?? prompts/extract_grounded.md`
   - Part 5 由来: `?? tools/apply_freshness_2026_06_04.py` (Part 5 の一回限りスクリプト)
   - Part 4 継続: `?? tools/eval_blind_judge.py` / `eval_fabrication_fix.py` / `eval_local_extraction.py` / `llm_local.py`
   - 残す / 廃棄 / 別 commit にまとめるかをユーザーと相談 (テーマ違うので別 commit にして整理が自然)

4. **run_daily.py 試走** (Part 5 低5 継承)
   - **Gemini API 課金発生 → 事前承認必須**
   - 通過後に `audit_urls --gate` を再走

5. **modules.future 1 件のみ entity に 2 件目追加** (Part 5 低6 継承)
   - deepseek / chatgpt / 他 multi-entity で `future` が 1 件のみのものを調査して 2 件目を追加
   - 全 entity の `modules.future` 件数調査未実施

### 任意 (恒久対策メモリ追記候補・本セッション派生)

6. **memory: 鮮度レビューは history 先頭 + now=true 位置を必ず確認**
   - Part 5 事故 (末尾 3 件だけ見て二重 prepend) + 本セッションでは事前全件確認で再発防止確認済み
   - `feedback_impact_analysis_before_modification` に「鮮度レビュー時の history 確認手順」を追記、または新規 `feedback_freshness_review_head_first` として独立

7. **memory: `[hidden] + display:grid/flex` 既知バグ**
   - 本セッションで AI-Pulse の theme.css に境界集約済の経緯を memory 化
   - `feedback_check_design_principles` の §2 (境界 1 箇所集約) の具体例として追記、または `feedback_web_ui_e2e_test` の事例追加
   - 「`el.hidden` プロパティ確認だけでは不十分、`computedDisplay` も見る」を E2E 検証手順に追加

8. **memory: 段階修正連発 (5+ 回同一ファイル編集)**
   - 本セッションで `templates/index.html.j2` を 7+ 回編集 (warn_repeated_edit_same_file hook が 5 回目で発火)
   - 初手の観察不足の兆候として `feedback_real_environment_first_verification` または `feedback_impact_analysis_before_modification` に追記

---

## 3. 守るべき制約 (Part 5 から継続 + 本セッション追加)

- **54 PASS を一切いじらない**: 新規追加は OK、既存削除 / 変更は理由を明示
- **DESIGN.md トークン経由で色・余白指定**: `var(--cat)` `var(--accent)` 等 (直書き禁止)
- **コミット & push は明示 GO 待ち**
- **新規 entity 追加は同 category に 2 件以上ある時点で `comparison.cols` 必須** (`tests/test_schema.py::test_comparison_is_required_when_category_has_peers` で locked-in)
- **`history[].url` / `modules.future[].url` / `event.source_url` は WebSearch / WebFetch + urllib HEAD/GET で実機 200 確認したものだけ書く** (LLM 捏造 ban、[AI-Pulse/CLAUDE.md](../CLAUDE.md) §URL 偽造防止)
- **push 前は必ず `./.venv/Scripts/python.exe tools/audit_urls.py --gate` を通す** (exit 0 = 直近 14 日 URL 健全)
- **Gemini API 呼び出しは事前確認**: `run_daily.py` 起動はユーザー GO 待ち
- **鮮度レビューで history に新エントリ追加する前は、history 先頭 3 件と `now=true` 位置を全件確認する** (Part 5 事故 + 本セッション再発防止確認)
- **[新] アセット変更 (templates/ / static/css|js|svg|png) を含む commit は `static/sw.js` の CACHE 名 bump 必須** (safe-commit ゲート 6 が拒否する)
- **[新] `[hidden]` 属性は theme.css の `[hidden]{display:none!important}` で物理保証される** が、本ガード前提で各画面 CSS を書くこと (個別の display:grid/flex 指定で [hidden] が見えてしまう経路は理論上ゼロ化済)

---

## 4. 重要ファイル参照 (次セッション冒頭読み推奨)

| ファイル | 役割 |
|---|---|
| [docs/handoff_2026-06-05_session_close.md](handoff_2026-06-05_session_close.md) | 本ファイル (最新) |
| [docs/handoff_2026-06-04_session_close_part5.md](handoff_2026-06-04_session_close_part5.md) | Part 5 (鮮度 Part 2 着手前) |
| [CLAUDE.md](../CLAUDE.md) | プロジェクト規範 + URL 偽造防止 push 前必須手順 |
| [DESIGN.md](../DESIGN.md) | デザイントークン |
| [tools/schema.py](../tools/schema.py) | entity / event の境界バリデータ + LENS_AXES |
| [tools/generate_pages.py](../tools/generate_pages.py) | SSG 本体 (32 ページ: feed 15 / archive 107 / karte 29) |
| [tools/validate_urls.py](../tools/validate_urls.py) | URL 検証 3 段プローブ境界 |
| [tools/audit_urls.py](../tools/audit_urls.py) | URL 一括監査 CLI (`--gate` で push 前ゲート、159/159 OK) |
| [tools/apply_freshness_2026_06_04_part2.py](../tools/apply_freshness_2026_06_04_part2.py) | 本セッション一回限り鮮度反映スクリプト (commit 同梱済) |
| [tools/check_freshness_urls_part6.py](../tools/check_freshness_urls_part6.py) | 本セッション一回限り URL 200 チェッカー (commit 同梱済) |
| [tests/test_urls_live.py](../tests/test_urls_live.py) | URL 生存契約テスト |
| [data/entities.jsonl](../data/entities.jsonl) | 全 29 カルテ (本セッションで 15 件鮮度更新済・commit `f7cc1e4` 同梱) |
| [tests/test_schema.py](../tests/test_schema.py) | スキーマ契約テスト |
| [tests/test_generate.py](../tests/test_generate.py) | SSG 契約テスト |
| [templates/index.html.j2](../templates/index.html.j2) | トップフィード template (UI 拡大反映済・スコア⇔画像隙間詰めは未コミット) |
| [static/theme.css](../static/theme.css) | デザイントークン CSS + `[hidden]{display:none!important}` 境界ガード (`f7cc1e4` で追加) |
| [static/sw.js](../static/sw.js) | PWA Service Worker (CACHE=`aipulse-v8`、`f7cc1e4` で bump) |

---

## 5. このセッションで守った memory feedback

- `feedback_handoff_inventory_diff_closeout`: Part 5 残 15 件を起点に、本ファイルでも残タスクを「Part 5 受領全量 − 本セッション done + 派生」の差分で列挙
- `feedback_impact_analysis_before_modification`: 鮮度レビューで全件確認版を作り Part 5 二重 prepend 事故を再発防止 + タグフィルターは実機 DOM 観察で真因 (CSS specificity) を特定
- `feedback_real_environment_first_verification`: タグフィルター「動いている」を mental model で確定せず、chrome-devtools MCP で `getComputedStyle` まで見て初めて真因に到達
- `feedback_llm_url_fabrication_ban`: 新規 22 URL 全てを WebSearch / WebFetch + validate_urls 3 段プローブで 200 確認 (cnbc.com 等の alt も含む)
- `feedback_test_before_report`: pytest 54 PASS + audit_urls 159/159 OK + chrome-devtools 実機検証 (hidden=true → computedDisplay=none 確認) の実測値を含めて報告
- `feedback_check_design_principles`: タグフィルター修正を段位 5 (個別 smoke) でなく段位 2 (境界 1 箇所集約) で恒久封じ込め
- `feedback_web_ui_e2e_test`: `el.hidden` プロパティだけでなく `computedDisplay` + `visibleHeight` まで見ないと CSS specificity バグを見逃すことを実体験で確認
- `feedback_intent_over_wording`: ユーザー割り込み (サムネ拡大 / スコア 2 倍 / 隙間詰め) を字面でなく「トップフィード可読性向上」の意図にまとめて 1 commit に束ねた (1 commit 方針はユーザー明示確認)
- `feedback_remote_push_marker_judgment`: ユーザー明示指示 (「2 をやってから push まで」「push して」) のみ CLAUDE_PUSH_CONFIRMED marker を末尾に付けて通した
- `feedback_token_efficiency`: 本セッション末で文脈肥大 (turns=174, cache_read=283K=baseline×5.3) を Stop hook 検知 → `/clear` 提案 (引き継ぎ書作成優先で実行待ち)

---

## 6. 次セッション起動方法

### Claude Code CLI (ローカル)

ファイルパス渡し:

```
AI-Pulse/docs/handoff_2026-06-05_session_close.md
```

### claude.ai ブラウザ版に貼る場合 (self-contained プロンプト)

> AI-Pulse プロジェクト (生成 AI 特化ニュース + DB の Jinja2 SSG + PWA) を `HIDEPON-UMG/AI-Pulse` private repo で運用しています (origin/master HEAD = `f7cc1e4`、直前セッションで 6 ファイル commit + push 済)。
>
> **直前セッション (2026-06-05) までの主要状態**:
> - 全 29 entity (agent 5 / editor 5 / infra 3 / media 4 / model 7 / physical 3 / policy 2) 全件 `comparison.cols` 完備 + 全件 snapshot_date=2026-06-04
> - 直前セッション `f7cc1e4` で **15 entity の鮮度更新**を data/entities.jsonl に適用済 (commit 済):
>   - tesla-optimus: Optimus Gen 3 pilot 開始 + V3 reveal 延期
>   - runway: Gen-4.5 (2025.12)
>   - dify: 1.14.2 + MCP 統合 + Supervisor agent
>   - langgraph: LangGraph 1.0 GA (2025.10)
>   - openclaw: v2026.5 系列 (Skill Workshop + plugin packaging)
>   - cosmos: Cosmos 3 詳細強化 (mixture-of-transformers + Cosmos Coalition)
>   - ironwood-tpu: Anthropic 1M TPU 構想 + Broadcom $10B 契約
>   - vera-rubin: 2026.06 Rubin full production
>   - flux: 2026.03 Speed Upgrade
>   - figure: Helix 02 で 8h 連続自律シフト + 寝室再構築
>   - eu-ai-act: **重要** 高リスク AI 期限 2026.08→2027.12 延期合意
>   - japan-ai-act: AI 基本計画閣議決定 (2025.12.23)
>   - devin: Windsurf 完全リブランド (Devin Local Rust + ACP プロトコル)
>   - agentkit: **重要** Agent Builder 2026.11.30 廃止予告
>   - physical-intelligence: snapshot のみ更新 (新リリース無し)
> - **重大バグ修正**: タグフィルターが効かない事象を `static/theme.css` に `[hidden]{display:none!important}` 境界ガードで恒久封じ込め (`.story{display:grid}` 等が UA `[hidden]{display:none}` を CSS specificity で打ち負かす経路をゼロ化)
> - トップフィード UI: サムネ 1.5x (200→300px) + カルテボタン 1.5x (15→22px) + スコア 2x (28→56px、列幅とレスポンシブも連動)
> - PWA: CACHE `aipulse-v7` → `v8` bump
> - URL 偽造防止構造稼働、push 前 `./.venv/Scripts/python.exe tools/audit_urls.py --gate` で 159/159 OK
> - pytest 54 PASS / SSG 32 ページ (feed 15 / archive 107 / karte 29)
>
> **未コミット差分** (本セッション末尾派生・push 後の追加要望):
> - `templates/index.html.j2`: スコア⇔画像隙間詰め (親 grid 列 160→100px、横 gap `var(--s-24)`→`var(--s-8)`、タブレット 128→80)
>   - 視覚確認済 (chrome-devtools MCP) でスコア「55」と画像が隣接
>   - 単独 commit + push で消化したい
>
> **次に着手したい優先順**:
> 1. 直前セッション末尾の未コミット (スコア⇔画像隙間詰め) を単独 commit + push — safe-commit ゲート通過
> 2. モバイル 390px 真幅 E2E (chrome-devtools MCP の `emulate` ツールで実機検証) — スマホ列幅 96px / num 36px / カルテ chip 15px が崩れていないか
> 3. 未追跡ファイル整理判断 (Ollama qwen3 評価系 `?? docs/eval/*` + `?? tools/eval_*.py` + `?? tools/llm_local.py` + `M tools/config.py` + Part 4 `?? handoff_*.md` 4 本 + `?? tools/apply_freshness_2026_06_04.py` Part 5 一回限り + `?? prompts/extract_grounded.md`)
> 4. run_daily.py 試走 (Gemini API 課金 → 要承認)
> 5. modules.future 1 件のみ entity (deepseek 等) に 2 件目追加
> 6. (任意) 恒久対策メモリ追記: 鮮度レビューは history 先頭+now=true 位置を必ず確認 / `[hidden]+display:grid` 既知バグ / 段階修正連発 (5+ 同一ファイル編集) の警戒
>
> **制約**:
> - 既存 54 PASS 維持 (削除前は理由明示)
> - コミット・push は明示 GO 待ち
> - DESIGN.md トークン経由で色指定 (`var(--cat)` `var(--accent)` 等、直書き禁止)
> - history[].url / modules.future[].url / event.source_url は WebSearch + urllib で 200 確認したものだけ書く (LLM 捏造 ban)
> - push 前は `./.venv/Scripts/python.exe tools/audit_urls.py --gate` を必ず通す
> - 同 category 2 件以上の entity は `comparison.cols` 必須 (LENS_AXES 全軸を `{v, r}` 形式で埋め)
> - 鮮度レビューで history に新エントリ追加する前は、必ず先頭 3 件と now=true 位置を全件確認する (Part 5 事故の教訓)
> - アセット変更を含む commit は `static/sw.js` の `CACHE` bump 必須 (safe-commit ゲート 6 が拒否)
>
> **entity スキーマ**:
> - 必須: `entity_id, name, kind, domain, offering, vendor, category, snapshot_date, positioning`
> - 任意 (条件付き): `comparison: {cols: [{name, self?, cells: {axis: {v, r?}}}]}`, `history: [{when, title, note?, source?, url?, now?}]`, `modules: {future: [{label, title}]}`, `competitors`, `relations`, `recommendation, confidence`, `overview`
> - enum: `category={model,editor,media,agent,infra,policy,physical}`, `kind={model,runtime,app,library,repo,hardware,regulation}`, `offering={oss,saas,commercial,hybrid,public}`
>
> **LENS_AXES (category 別の comparison 軸)**:
> - model: `strength, context, mm_in, mm_out, ecosystem, pricing` (6 軸)
> - editor: `iface, auto, strength, mcp, pricing` (5 軸)
> - agent: `autonomy, tools, strength, extensibility, pricing` (5 軸)
> - media: `offering, strength, control, video, license` (5 軸)
> - infra: `offering, scale, strength, integration, pricing` (5 軸)
> - policy: `scope, binding, topic, target, timing` (5 軸)
> - physical: `form, hardware, foundation, autonomy, strength` (5 軸)
>
> ブラウザ版では実コードを読めないので、必要なファイルがあれば手元で開いて該当部分を貼ってください。
