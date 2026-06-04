# 次セッション引継ぎ — 2026-06-04 セッションクローズ Part 4

作成: 2026-06-04 (本セッション末)
直近 push 済: `8a16744` (= origin/master HEAD)。

前 handoff:
- [docs/handoff_2026-06-04_session_close.md](handoff_2026-06-04_session_close.md) (Part 1)
- [docs/handoff_2026-06-04_session_close_part2.md](handoff_2026-06-04_session_close_part2.md) (Part 2)
- [docs/handoff_2026-06-04_session_close_part3.md](handoff_2026-06-04_session_close_part3.md) (Part 3 — `e4d33c7` までの中間状態)

> **Part 3 → Part 4 の差分**: Part 3 で「高1 (Qwen 3.7 化) / 高2 (media レンズ追加)」が残課題として記載されていたが、その後の `8a16744` で**両方とも完了して push 済**。本ファイルは現状反映の最新版。

---

## 1. Part 3 → 本ファイル時点の新規 commit (1 本、push 済)

| sha | 概要 |
|---|---|
| [`8a16744`](https://github.com/HIDEPON-UMG/AI-Pulse/commit/8a16744) | URL 偽造防止構造を導入し既存 7 件の捏造 URL を修正 + Qwen 系カルテ拡充 |

### `8a16744` の達成事項

- **URL 偽造防止構造の本実装**: News-Grasp の 3 段プローブを AI-Pulse に移植
  - `tools/validate_urls.py` (境界モジュール、`UrlFabricationError` を raise する `require_live_urls()` を持つ)
  - `tools/audit_urls.py` (CLI、`--gate` / `--recent N` / `--max-workers N` をサポート)
  - `tests/test_urls_live.py` (契約テスト、subprocess で audit_urls --gate を呼ぶ二重ガード)
  - [AI-Pulse/CLAUDE.md](../CLAUDE.md) に push 前必須手順を追記
- **既存 7 件の捏造 URL 修正**:
  - 5 件は WebSearch で正規 URL に差し替え
  - 2 件 (windsurf wave 8 / windsurf launch / tesla-optimus 系) は公式 URL なしのため URL のみ削除し source 名だけ残置
- **Qwen カルテを Qwen3.6 系列に大幅更新**:
  - ユーザー言及の「3.7」は公式リポ調査で**不存在**と判明 → **3.6 で確定**
  - history: Qwen2.5 (2024.09) → Qwen3 (2025.04) → Qwen3-Omni (2025.09) → Qwen3.5 (2026.02) → Qwen3.5 Dense (2026.03) → Qwen3.6-35B-A3B (2026.04) → Qwen3.6-27B (2026.04) → NVIDIA Qwen3.6-35B-A3B-NVFP4 (2026.05) の **8 件**
  - 全件 `url` 付き (audit_urls 200 確認済)
- **media レンズに 2 件追加** (Part 3 で残課題だった項目):
  - `qwen-image`: Qwen-Image (20B MMDiT)
  - `anima-base`: Anima Base v1.0 (CircleStone Labs)

### 検証実測値 (本セッション末)

- **pytest 54 PASS** (`./.venv/Scripts/python.exe -m pytest -q`、所要 30.39s)
- **audit_urls --gate: 141/141 OK, 0 NG** (`./.venv/Scripts/python.exe tools/audit_urls.py --gate`)
- **entity 総数 29 件** (Part 3 末 27 件 + qwen-image + anima-base)
  - agent: 5 / editor: 5 / infra: 3 / media: 4 / model: 7 / physical: 3 / policy: 2
  - **全 29 件が `comparison.cols` 完備**

---

## 2. 残課題 (次セッションで着手・delivered - done の差分)

### 中

1. **既存 21 カルテの鮮度レビュー** (Part 3 中3 を継承、依然未着手)
   - 大半の `snapshot_date` が 2026-06-03、ただし `positioning` / `history` の現在妥当性は未確認
   - 優先: 業界変化の激しいレンズ (model / editor) と最古 5 件
   - 鮮度確認は WebSearch + WebFetch、追加 URL は `audit_urls --gate` 通過後

2. **モバイル 390px 真幅 E2E** (Part 3 中4 を継承、依然未着手)
   - chrome-devtools MCP の resize は ~501px 最小幅クランプ
   - device emulation API (`emulate` ツール) で 390px 真幅検証

### 低

3. **未追跡ファイルの整理判断** (Part 3 低5 を継承、作業ツリーに残存)
   - 作業ツリー残物の現状 (`git status` 実測):
     - `M tools/config.py` (Ollama qwen3 backend 切替)
     - `?? docs/eval/2026-06-04_blind_judge.md` / `_blind_judge_raw.json`
     - `?? docs/eval/2026-06-04_fabrication_fix.md` / `_fabrication_fix_raw.json`
     - `?? docs/eval/2026-06-04_local_llm_investigation.html` / `.md`
     - `?? docs/eval/2026-06-04_qwen3_vs_gemini.md`
     - `?? docs/handoff_2026-06-04_karte_polish_pending.md`
     - `?? docs/handoff_2026-06-04_session_close.md` / `_part2.md` / `_part3.md` / `_part4.md` (本ファイル含む)
     - `?? prompts/extract_grounded.md`
     - `?? tools/eval_blind_judge.py` / `eval_fabrication_fix.py` / `eval_local_extraction.py` / `llm_local.py`
   - 判断: ローカル LLM (Ollama qwen3) 評価系を残すか / 廃棄するか / 別 commit にまとめるか をユーザーと相談

4. **`run_daily.py` を 1 度走らせて新プロンプト + ゲート動作確認** (Part 3 低6 を継承)
   - **Gemini API 課金発生 → 事前承認必須**
   - 通過後に `audit_urls --gate` を再走

5. **`modules.future` が 1 件しかない entity (deepseek 等) に 2 件目追加** (Part 3 低7 を継承)
   - 全 entity の `modules.future` 件数調査未実施

---

## 3. 守るべき制約 (継続)

- **54 PASS を一切いじらない**: 新規追加は OK、既存削除/変更は理由を明示
- **DESIGN.md トークン経由で色・余白指定**: `var(--cat)` `var(--accent)` 等 (直書き禁止)
- **コミット & push は明示 GO 待ち**
- **新規 entity 追加は同 category に 2 件以上ある時点で `comparison.cols` 必須** (`tests/test_schema.py::test_comparison_is_required_when_category_has_peers` で locked-in)
- **`history[].url` / `modules.future[].url` / `event.source_url` は WebSearch/WebFetch + urllib HEAD/GET で実機 200 確認したものだけ書く** (LLM 捏造 ban、[AI-Pulse/CLAUDE.md](../CLAUDE.md) §URL 偽造防止)
- **push 前は必ず `./.venv/Scripts/python.exe tools/audit_urls.py --gate` を通す** (exit 0 = 直近 14 日 URL 健全)
- **Gemini API 呼び出しは事前確認**: `run_daily.py` 起動はユーザー GO 待ち

---

## 4. 重要ファイル参照 (次セッション冒頭読み推奨)

| ファイル | 役割 |
|---|---|
| [docs/handoff_2026-06-04_session_close_part4.md](handoff_2026-06-04_session_close_part4.md) | 本ファイル (最新) |
| [docs/handoff_2026-06-04_session_close_part3.md](handoff_2026-06-04_session_close_part3.md) | Part 3 (`e4d33c7` までの中間状態、`8a16744` 反映前) |
| [CLAUDE.md](../CLAUDE.md) | プロジェクト規範 + URL 偽造防止 push 前必須手順 |
| [DESIGN.md](../DESIGN.md) | デザイントークン |
| [tools/schema.py](../tools/schema.py) | entity / event の境界バリデータ + LENS_AXES |
| [tools/generate_pages.py](../tools/generate_pages.py) | SSG 本体 |
| [tools/validate_urls.py](../tools/validate_urls.py) | URL 検証 3 段プローブ境界 (新規 `8a16744`) |
| [tools/audit_urls.py](../tools/audit_urls.py) | URL 一括監査 CLI (`--gate` で push 前ゲート、新規 `8a16744`) |
| [tests/test_urls_live.py](../tests/test_urls_live.py) | URL 生存契約テスト (新規 `8a16744`) |
| [templates/karte-index.html.j2](../templates/karte-index.html.j2) | カルテ一覧テンプレ |
| [data/entities.jsonl](../data/entities.jsonl) | 全 29 カルテ |
| [tests/test_schema.py](../tests/test_schema.py) | スキーマ契約テスト |
| [tests/test_generate.py](../tests/test_generate.py) | SSG 契約テスト |

---

## 5. このセッションで守った memory feedback (Part 4 セッション分)

- `feedback_handoff_inventory_diff_closeout`: 着手前にユーザー指示「高1 + 高2」を鵜呑みにせず、`git log` 実測で `8a16744` で完了済を発見し二重実装を回避。残タスクは「受領全量 - 実装済」の差分で列挙
- `feedback_self_collect_diagnostics`: handoff 記載と実際の HEAD の食い違いを `git log --oneline` / `git status` / 直接 entity 確認で自己解明
- `feedback_no_speculation`: Qwen 3.7 のような未確認情報はユーザー指摘でも「公式リポで不存在」と裏取りした上で 3.6 に確定 (`8a16744` メッセージに記録)
- `feedback_llm_url_fabrication_ban`: URL 偽造防止構造を本実装、push 前ゲート (`audit_urls --gate`) を `141/141 OK` で確認
- `feedback_test_before_report`: pytest 54 PASS と audit_urls 141/141 OK の実測値を含めて報告
- `feedback_intent_over_wording`: 着手前に「次のアクション」を 4 択で確認、Part 4 作成を選んでもらってから書き出した

---

## 6. 次セッション起動方法

### Claude Code CLI (ローカル)

ファイルパス渡し:
```
AI-Pulse/docs/handoff_2026-06-04_session_close_part4.md
```

### claude.ai ブラウザ版に貼る場合 (self-contained プロンプト)

> AI-Pulse プロジェクト (生成 AI 特化ニュース + DB の Jinja2 SSG + PWA) を `HIDEPON-UMG/AI-Pulse` private repo で運用しています (origin/master HEAD = `8a16744`)。
>
> **直前セッション (2026-06-04 Part 4 時点)** までに完了している主要作業:
> - 29 entity (agent 5 / editor 5 / infra 3 / media 4 / model 7 / physical 3 / policy 2) 全件 `comparison.cols` 完備
> - Qwen カルテは Qwen3.6 系列 + NVFP4 量子化 history まで反映 (公式に「3.7」は不存在のため 3.6 で確定)
> - media レンズに Qwen-Image / Anima Base v1.0 追加済
> - URL 偽造防止構造 (`tools/validate_urls.py` + `tools/audit_urls.py` + `tests/test_urls_live.py`) が稼働、push 前は `audit_urls --gate` で 141/141 OK
> - pytest 54 PASS / SSG 30 ページ (karte 29)
>
> **次に着手したい優先順**:
> 1. 既存 21 カルテの鮮度レビュー (model/editor 優先、最古 5 件)
> 2. モバイル 390px 真幅 E2E (chrome-devtools MCP の resize は ~501px クランプのため device emulation で)
> 3. 未追跡ファイルの整理判断 (Ollama 評価系 + handoff_*.md 4 本 + `M tools/config.py`)
> 4. `run_daily.py` 試走 (Gemini API 課金発生 → 要承認)
> 5. `modules.future` 1 件のみ entity (deepseek 等) に 2 件目追加
>
> **制約**:
> - 既存 54 PASS 維持 (削除前は理由明示)
> - コミット・push は明示 GO 待ち
> - DESIGN.md トークン経由で色指定 (`var(--cat)` `var(--accent)` 等、直書き禁止)
> - `history[].url` / `modules.future[].url` / `event.source_url` は WebSearch + urllib で 200 確認したものだけ書く (LLM 捏造 ban)
> - push 前は `./.venv/Scripts/python.exe tools/audit_urls.py --gate` を必ず通す
> - 同 category 2 件以上の entity は `comparison.cols` 必須 (LENS_AXES 全軸を `{v, r}` 形式で埋め)
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
