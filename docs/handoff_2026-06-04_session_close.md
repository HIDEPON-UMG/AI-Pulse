# 次セッション引継ぎ — 2026-06-04 セッションクローズ

作成: 2026-06-04 (本セッション末)
直近 commit: [`f3331cb`](../README.md) push 済 (origin/master = HIDEPON-UMG/AI-Pulse)

---

## 1. 今回セッションで完了したこと

### コミット済 (`f3331cb`)

入力 handoff: `docs/handoff_2026-06-04_karte_polish_pending.md` の 3 件 + ユーザー追加要件 4 件を実装。

| # | 内容 | 影響ファイル |
|---|---|---|
| 1 | カルテ将来シナリオの時間軸ラベル「近/中/遠」を Noto Serif JP 28px + accent→cat 対角グラデ | `templates/karte.html.j2` |
| 2 | カルテ最下段「関連ニュース」セクション追加 (主+ related_entities 一致イベント全件・新しい順) + 契約テスト 1 件 | `tools/generate_pages.py` / `templates/karte.html.j2` / `tests/test_generate.py` |
| 3 | フィードトップ動的タイトルに News-Grasp 風下半マーカー (主語+カテゴリ名を `<mark>` 化) | `static/app.js` / `templates/index.html.j2` |
| A | `.story` に `SUMMARY` / `EVALUATE` 区切り線 + `details.why` を EVALUATE 下へ移動 | `templates/index.html.j2` |
| B | タイトル 22→25px / 本文 14-15→16-17px / feature h2 27→30px / 本文+判断理由にカテゴリ薄背景 (7%/5%) + 左帯 (45%) | `templates/index.html.j2` / `templates/karte.html.j2` |
| C | 本文強調 3 種を意味分け+視覚分離: **太字**=固有名 (fontweight) / ==マーカー==下半塗り (News-Grasp 風) / __下線__=波線+semi-bold | `templates/index.html.j2` / `templates/karte.html.j2` |
| D | archive A 改修 (h3 16→18px + summary-short カテゴリ 6% 薄背景 + 左帯 35% + entry 左帯 45% mix で統一) | `templates/archive.html.j2` |
| E | 既存 events を Sonnet (`tools/rewrite_emphasis.py` 決定論ルール) で振り直し: `==マーカー== 44→105件 (+61)` / `__下線__ 22→41件 (+19)` / 太字以外を 1 つ以上使う event 58% | `tools/rewrite_emphasis.py` (新規) / `data/events.jsonl` |
| F | Gemini プロンプト強化: 3 種記法の絶対条件 + 良/悪例を明記 | `prompts/gemini_summarize.md` |
| G | 契約ゲート: `llm_gemini._check_shape` に `EmphasisShortageError` 追加。太字一色応答は 1 回 retry → 2 回連続でドロップ | `tools/llm_gemini.py` / `tests/test_llm_gemini.py` (+2 件) |
| H | archive `summary_short` は記法 plain 化 (密圧縮役割の分離) | `tools/generate_pages.py` |

### 検証結果

- **51 PASS** (48→+3: `test_emphasis_only_bold_retries_once` / `test_emphasis_no_marks_at_all_fails` / `test_existing_events_use_diverse_emphasis` / `test_karte_feed_items_include_main_and_related_events`)
- **DESIGN.md lint errors=0** (warnings 30 は既存トークンの未参照、infos 1)
- **E2E 検証** (chrome-devtools MCP):
  - desktop 1280x900 / モバイル幅 501px (ブラウザ最小幅クランプで真の 390 ではない)
  - 実 DOM 値で全改修確認: h2=30px / li=16px / 薄背景 7% / 左帯 45% / mark 下半塗り / u 波線下線
  - karte-claude-opus で 3 種記法実機検出 (mark 2 / u 1 / b 27)
- **スクショ**: `docs/eval/2026-06-04_task{1..5}_*.png` 6 枚

---

## 2. 既知の制約 (次セッションへ持ち越す前提)

### A. 本日フィード (index.html) の 3 種記法は薄い

- ref date = `2026-06-04` の publshed 15 件は rewrite_emphasis で振り直し済だが、データの性質上 ==/__ がほぼ含まれない event がある (数値/動作キーワードが summary に存在しない記事)
- カルテページの「関連ニュース」 (過去含む) は 3 種が出ている
- 明日以降 `run_daily.py` で新プロンプト+ゲート経由の events が積み上がるにつれて、フィード本日分の 3 種利用率は上がる想定

### B. archive の `summary_short` は plain (記法削除)

- 60 字切り詰めで記号残りを防ぐため `_summary_short` で `**==__` を全削除
- フィードと役割分離 (archive=俯瞰インデックス / feed=詳細濃い読み物)

### C. モバイル真幅は未検証

- chrome-devtools MCP の `resize_page(390, 844)` はブラウザ最小幅クランプで innerWidth=501 に固定された
- memory `feedback_real_environment_first_verification` の方針では device emulation で 390 を検証すべき
- レイアウト崩れは無いが、390px 真幅での検証は次セッションでオプション

### D. `modules.future` が 1 件しかない entity が複数

- 例: `deepseek` カルテは将来シナリオ 1 件 (「近」のみ)、本来 3 件 (近/中/遠) 想定
- entities.jsonl の modules.future を 2 件以上に増やすかは別判断

---

## 3. 未追跡ファイル (前セッション/別作業ぶん、commit 除外)

```
M tools/config.py                      # Ollama qwen3 backend 追加 (前セッション)
?? tools/eval_local_extraction.py       # Ollama eval スクリプト (前セッション)
?? tools/llm_local.py                   # Ollama wrapper (前セッション)
?? docs/eval/2026-06-04_qwen3_vs_gemini.md  # Ollama 比較メモ (前セッション)
?? docs/handoff_2026-06-04_karte_polish_pending.md  # 今回の入力 handoff (作業消化済)
?? docs/handoff_2026-06-04_session_close.md  # 本ファイル
```

### 判断保留事項

- **Ollama qwen3 系の commit 要否**: 前セッションが「flash-lite と差が無いため動機にならない」と config.py コメントに書いている。動かして実用判断するか、未追跡のまま据え置くか
- **`docs/handoff_2026-06-04_karte_polish_pending.md` の取り扱い**: 内容は今回で消化済。削除 (git 履歴で参照可能) / done リネーム / そのまま据え置きのいずれか

---

## 4. 次セッションで着手しうるタスク (優先度順)

### 高 (短時間でリスク低)

1. **本ファイル + handoff_karte_polish_pending.md の整理**: done リネームか削除を決めて 1 コミット
2. **Ollama 系未追跡ファイルの commit 判断**: ユーザーに方針を聞いて 1 コミット or 削除

### 中 (要ユーザー判断 / 動作確認)

3. **`run_daily.py` を 1 度走らせて新プロンプト+ゲート動作確認**:
   - Gemini API 呼び出しが発生 (RPM 制限・少額課金) → 事前確認必須
   - 期待: 新 events が `==マーカー==` `__下線__` を使い分けて生成される、太字一色は EmphasisShortageError で retry → 修正版 OK
4. **DESIGN.md の orphaned-tokens 30 件 warning 整理**: 一部は意図的 (直接参照前提) なので token 単位で要判断
5. **モバイル 390px 真幅 E2E**: chrome-devtools MCP の emulate_device で再検証

### 低 (改善要望ベース)

6. **`modules.future` が 1 件しかない entity に 2 件目追加**: deepseek / dify / runway 等
7. **archive のフィルタ範囲拡大**: 現状 SCORE_MIN 通過分のみ、全件取得への変更可否
8. **HTML 仕様書 (`docs/specs/*.html`) の本回改修反映**: アーキ自体は不変だがフィード仕様は更新余地あり

---

## 5. 重要ファイル参照 (次セッション冒頭読み推奨)

| ファイル | 役割 |
|---|---|
| [docs/handoff_2026-06-04_session_close.md](handoff_2026-06-04_session_close.md) | 本ファイル |
| [CLAUDE.md](../CLAUDE.md) | プロジェクト規範 |
| [DESIGN.md](../DESIGN.md) | デザイントークン (色/タイポ/余白) |
| [static/theme.css](../static/theme.css) | トークン実装 |
| [prompts/gemini_summarize.md](../prompts/gemini_summarize.md) | Gemini プロンプト (絶対条件 + 例) |
| [tools/llm_gemini.py](../tools/llm_gemini.py) | API 境界 + emphasis 契約ゲート |
| [tools/rewrite_emphasis.py](../tools/rewrite_emphasis.py) | Sonnet 担当の決定論 rephrase |
| [tests/test_generate.py](../tests/test_generate.py) | データ集計契約テスト |
| [tests/test_llm_gemini.py](../tests/test_llm_gemini.py) | LLM 境界契約テスト |

---

## 6. 守るべき制約 (前セッション継続)

- **既存 51 PASS を一切いじらない**: 新規追加は OK、既存削除/変更前は理由を明示
- **DESIGN.md トークン経由で色・余白指定**: `var(--cat)` `var(--accent)` 等。直書き禁止
- **コミットは明示 GO 待ち / push は明示 GO + marker `# CLAUDE_PUSH_CONFIRMED` 待ち**
- **スキーマ変更を伴わない**: 既存 events.jsonl / entities.jsonl の構造は不変 (新フィールド追加は OK)
- **Gemini API 呼び出しは事前確認**: コスト発生のため、`run_daily.py` 起動はユーザー GO 待ち

---

## 7. このセッションで守った memory feedback (継続要)

- `feedback_impact_analysis_before_modification`: 改修前に Grep で全呼出元列挙
- `feedback_match_advice_against_memory`: 提案手法を MEMORY.md と中身で照合
- `feedback_no_speculation`: 「未確認」前置きを徹底、推測で UI 構造を断定しない
- `feedback_real_environment_first_verification`: 実機 DOM 観察 + 計測で確認 (resize クランプ問題も把握済)
- `feedback_web_ui_e2e_test`: chrome-devtools MCP で computed style 実測、curl だけで完了報告しない
- `feedback_test_before_report`: 全テスト 51 PASS 実測値を完了報告に含める
- `feedback_check_design_principles`: emphasis 違反は境界 1 箇所 (`_check_shape`) で物理ブロック (個別 smoke でなく)
- `feedback_remote_push_marker_judgment`: ユーザー明示「対応終わり次第 push」で marker 付与 OK と判定

---

**次セッションでの起動コマンド例**:
```
docs/handoff_2026-06-04_session_close.md
```
(ファイルパスを直接渡すと、Claude が冒頭から読んで状態把握できる)
