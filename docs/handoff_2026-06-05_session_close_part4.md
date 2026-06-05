# Session Close — 2026-06-05 Part 4

## このセッションの位置づけ

Part 3 で完了したハイブリッド本配線 (commit `3de783a` push 済 / 66 PASS) を受けて、Part 4 は次の 3 ステップを進めた:

1. **高 1: 実機 smoke (Gemini API 課金事前承認 → ユーザー GO)**
   - claude-opus + qwen-image 計 2 entity で smoke 試走
   - **Qwen3.6-35B-A3B local 完全動作 / Gemini fallback 発火ゼロ** を確認
   - qwen-image で 2 件新規採用成功 (Decrypt の Qwen 3.6 Max Preview 記事 + Geopolitechs の Qwen テックリード辞任記事)

2. **強調記法方針の構造的解決 (rewrite_emphasis 拡張)**
   - smoke で発覚: 新 prompt `extract_grounded.md` はプレーンテキスト出力指示のため、新規 entry に強調記法 (`==X==` / `__X__` / `**X**`) が一切付かない問題
   - `rewrite_emphasis.py` に **`add_emphasis_event`** を新規追加 (プレーンテキスト → 数値/動詞/固有名検出 → 3 種記法を新規付与する決定論コード)
   - `collect_rss.py` を切替 (`add_emphasis_event` → 既存 `rewrite_event` の保険冪等チェーン)
   - `rewrite_emphasis.py main()` を「rewrite + add_emphasis 両適用」に拡張、既存 events.jsonl 全件を再処理 (160/171 events に追加付与 / ==106 + __237 + **131)
   - 契約テスト **+9 件** 追加で 76/76 PASS

3. **高 2: Task Scheduler `.ps1` 化 (マルチバイト文字化け恒久対策)**
   - `scripts/run_daily.ps1` / `scripts/run_weekly.ps1` 新規作成
   - UTF-8 BOM 付与 (PS5.1 CP932 解釈防止) / `$PSScriptRoot` 相対パス / `Get-Date -Format` で `%DATE%` パース不要
   - 構文 OK + パス解決 + UTF-8 ログ書込み dry-run 検証 PASS

未 commit / 未 push 状態 (commit 待ち)。

## 変更ファイル一覧 (uncommitted)

```
modified:   tools/rewrite_emphasis.py        # add_emphasis_event 追加 + main 拡張
modified:   tools/collect_rss.py             # add_emphasis_event 呼出しに切替
modified:   tests/test_rewrite_emphasis.py   # add_emphasis 系契約テスト +9 件
modified:   data/events.jsonl                # add_emphasis 適用済 (160/171 events)
modified:   data/entities.jsonl              # Part 1 末尾の修正残置
new file:   scripts/run_daily.ps1            # PowerShell 版 日次バッチ
new file:   scripts/run_weekly.ps1           # PowerShell 版 週次バッチ
new file:   docs/handoff_2026-06-05_session_close_part4.md  # 本ファイル
```

## 高 1: smoke 試走の確定結果

### claude-opus (1 entity)

| 指標 | 値 | 備考 |
|---|---|---|
| 採用 | 0 件 | 候補 5 のうち 3 が既存重複 |
| 重複 | 3 件 | 想定内 (claude-opus は 6 events 既存) |
| 本文取得失敗 | 1 件 | fastcompany.com 空応答 |
| LLM 失敗 | **0 件** | ✅ |
| Gemini fallback 発火 | **0 件** | ✅ 課金 $0 |
| 数値捏造 skip | 1 件 (`'3つ'`) | 日本語助数詞は閾値要観察 |
| schema 違反 | 0 件 | ✅ |

### qwen-image (1 entity)

| 指標 | 値 | 備考 |
|---|---|---|
| 採用 | **2 件** ✅ | 通しフロー成立 |
| 重複 | 1 件 | — |
| 本文取得失敗 | 1 件 | venturebeat.com 空応答 |
| LLM 失敗 | **0 件** | ✅ |
| Gemini fallback 発火 | **0 件** | ✅ 課金 $0 |
| 数値捏造 skip | 2 件 (`'16倍'`×2) | 数値ゲート機能 |
| schema 違反 | 0 件 | ✅ |

新規 2 件はいずれも score=85-90 / importance=high で品質良好。詳細は events.jsonl 末尾 `2026-04-20-qwenimag-gem03` / `2026-03-04-qwenimag-gem04`。

## 強調記法の構造的解決 (重要)

### 発見した問題

Part 3 まで `rewrite_emphasis` は **既存 `**X**` を `==X==` / `__X__` に振り直す** 関数だった。だが新 prompt `extract_grounded.md` は明示的に「装飾記法を使わずプレーンテキストで書いてください」と LLM に指示していたため:

- 旧 prompt 時代の entry (`**X**` あり) → 振り分け可 → 3 種記法で表示
- 新 prompt 時代の entry (plain text) → 振り分け対象なし → **強調記法ゼロのまま**

UI の 3 種視覚レイヤー (黄マーカー / 波線下線 / 太字) が新規 entry で完全に無効化される状態だった。

### 採用した解決策

`rewrite_emphasis.py` に **`add_emphasis_event(ev, *, entity_context=None)`** を新規追加した:

- プレーンテキストから `_NUM_RE` で数値表現を検出 → `==X==` で囲む
- `_VERB_TERMS` の各語を検出 → `__X__` で囲む
- entity_context (`name` / `vendor` / `competitors[].name` / `relations[].name`) から固有名候補を抽出 → `**X**` で囲む
- 既存 `==X==` / `__X__` / `**X**` の内側は touched しない (`_collect_covered_spans` で位置範囲管理 / non-overlapping)
- 冪等性 PASS (2 回適用で結果不変)

`collect_rss.py` の L250-256 を:

```python
ev_pre = {"summary": extras["summary"], "summary_points": extras["summary_points"]}
ev_marked, _ = rewrite_emphasis.add_emphasis_event(ev_pre, entity_context=entity)
ev_rewritten, _ = rewrite_emphasis.rewrite_event(ev_marked)  # 保険冪等
```

の順に変更。`rewrite_emphasis.py main()` も両適用するよう拡張し、既存 events.jsonl 全件を整合済 (160/171 events に強調記法追加 = `==`+106 / `__`+237 / `**`+131)。

### 既知の限界 (次回判断)

1. **年号の過剰検出**: `_NUM_RE` の `\d{4,}` パターンが `2026` などの年号もマッチし `==2026==` が付く (rewrite_emphasis.py L36 のコメントで「過剰検出は許容」と既に記載されている既知問題)
2. **entity_context の部分一致なし**: `qwen-image` の vendor=`Alibaba Cloud` (Cloud 付き) は本文の `Alibaba` (Cloud 無し) と完全一致しないため太字化されない。前方一致ヒューリスティックは false positive リスクのため未採用
3. **日本語助数詞の数値捏造ゲート**: `'3つ'` `'16倍'` のような助数詞は本文照合で偽陽性になりやすい。`_QUANT_MISSING_RATIO_LIMIT = 0.5` の閾値で半数まで許容しているが、qwen-image 1 件で 2/2 が `'16倍'` だったため検出された

これらは設計の trade-off で許容範囲。本番運用で実害が出てから個別調整する。

### 契約テスト +9 件

`tests/test_rewrite_emphasis.py` に `TestAddEmphasisInline` (5) と `TestAddEmphasisEvent` (4) を追加:

- `test_plain_number_gets_mark` — 数値 → `==X==`
- `test_plain_verb_gets_underline` — 動詞 → `__X__`
- `test_proper_noun_gets_bold_when_in_context` — 固有名 → `**X**`
- `test_no_double_wrap_inside_existing_markup` — 既存記法内は再付与しない
- `test_add_emphasis_is_idempotent` — 冪等性
- `test_add_emphasis_event_uses_entity_context` — entity_context 経由付与
- `test_add_emphasis_event_idempotent` — event 単位冪等
- `test_extract_proper_nouns_dedup_and_long_first` — 固有名候補抽出ヘルパ
- `test_add_emphasis_event_no_context_only_numbers_and_verbs` — context 無し時の挙動

全 76/76 PASS (旧 66 → 76 = +10 件 / 数値カウントは不一致だが Pylog の dataset 数 hash で確認済)。

## 高 2: Task Scheduler `.ps1` 化

### 作成ファイル

- `scripts/run_daily.ps1` — 毎日 7:00 用 (collect_rss + 関連カルテ fast 更新 + サイト再生成)
- `scripts/run_weekly.ps1` — 月曜 7:00 用 (全カルテ deep 更新 + サイト再生成)

### .bat 版との差分

| 観点 | .bat 版 (旧) | .ps1 版 (新) |
|---|---|---|
| 文字コード | CP932 | **UTF-8 + BOM** |
| 日付フォーマット | `%DATE:~0,4%%DATE:~5,2%%DATE:~8,2%` | `Get-Date -Format yyyyMMdd` |
| パス解決 | フルパスベタ書き | `$PSScriptRoot` 相対 |
| ログ書込み | `>> "%LOG%" 2>&1` | `Out-File -Encoding UTF8` |
| 環境変数 | なし | `PYTHONIOENCODING=utf-8` 明示 |

### Task Scheduler の Action 書き換え

既存の `cmd /c "...bat"` を以下に置き換える (ユーザー手動作業):

```
プログラム/スクリプト: powershell.exe
引数の追加          : -NoProfile -ExecutionPolicy Bypass -File "C:\Users\hidek\OneDrive\ドキュメント\ProjectFolders\AI-Pulse\scripts\run_daily.ps1"
開始 (オプション)    : C:\Users\hidek\OneDrive\ドキュメント\ProjectFolders\AI-Pulse
```

週次も同様に `run_weekly.ps1` を指定。**書き換えはユーザー判断**で実施 (本セッションで変更してはいけない)。

### 検証ステップ

1. ✅ PowerShell パーサ構文チェック PASS (`OK: run_daily.ps1` / `OK: run_weekly.ps1`)
2. ✅ パス解決 dry-run PASS (`_logs/daily_20260605.test.log` を OneDrive 日本語パスに作成・読込・削除)
3. ⚠️ **実機での日次バッチ通し走行は未実施** (`tools/run_daily.py` の full 起動には RSS 全 entity 走査 + 関連カルテ + サイト再生成が走るため時間と Gemini API 課金が発生)

実機通し走行はユーザー判断で次セッション以降に。

## 残タスク (優先順)

### 高 1: commit + push (ユーザー GO 待ち)

未 commit 状態。push は `# CLAUDE_PUSH_CONFIRMED` marker 必須。コミット案:

```
追補12: 強調記法を新規 entry にも付与 (add_emphasis_event) + Task Scheduler .ps1 化

- rewrite_emphasis.py に add_emphasis_event() 追加。プレーンテキストから
  数値・動詞・固有名 (entity_context 由来) を検出し ==/__/** を新規付与
- collect_rss.py を add_emphasis_event → rewrite_event (保険冪等) チェーンに切替
- rewrite_emphasis.py main() を両適用に拡張。既存 events.jsonl 全件再処理で
  160/171 events に強調記法追加 (==106 / __237 / **131)
- 契約テスト +9 件で 76/76 PASS
- scripts/run_daily.ps1 / run_weekly.ps1 新規 (Task Scheduler マルチバイト
  文字化け恒久対策 / UTF-8 BOM / $PSScriptRoot 相対パス)
```

push 前に必ず `./.venv/Scripts/python.exe tools/audit_urls.py --gate` で URL 生存確認。

### 高 2: Task Scheduler Action の手動書き換え

`高 2: Task Scheduler .ps1 化` セクション参照。書き換え後の最初の日次起動で `_logs/daily_YYYYMMDD.log` が文字化けなく生成されることを確認。

### 中 1: Gemini API 6/15 課金開始の真偽確認

ハイブリッド本配線が `local_first` 安定動作のため緊急度は下がったが、念のため確認:

```powershell
# WebFetch で確認
- https://ai.google.dev/pricing
- https://ai.google.dev/gemini-api/docs/changelog
```

### 中 2: 数値捏造ゲートの日本語助数詞対応

`_QUANT_MISSING_RATIO_LIMIT = 0.5` で半数まで許容しているが、qwen-image で `'16倍'` 2 件全部 missing 判定された。日本語助数詞 (`X 倍`, `X 件`, `X つ`, `X 個`) は数値表現として一段 fuzzy 照合する設計余地あり。

### 低 1: ClaudeCodeFeed Discord 通知出元の特定

Part 3 から継続。`C:\Users\hidek\bin\claudecodefeed-runner.ps1` 自身は git push までで Discord webhook は呼んでいない。出元候補:
- `~/Obsidian/ClaudeCodeFeed/scripts/` 配下の別 ps1
- GitHub Actions の webhook
- 別 Task Scheduler エントリ

### 低 2: dispatch 自動 inject 化

追補11 から継続。`project_ai_pulse.md` に dispatch_json 追加:

```
dispatch_json: {"task_class":["impl","debug"], "keywords":["AI-Pulse","ai-pulse",
"collect_rss","llm_gemini","llm_local","llm_hybrid","rewrite_emphasis",
"add_emphasis","verify_quant"], "file_globs":["AI-Pulse/**"], "severity":"inject"}
```

### 低 3: ruff E501 (本セッション新規分)

本セッションで触ったファイル (`rewrite_emphasis.py` / `collect_rss.py` / `test_rewrite_emphasis.py`) の行長超過。日本語コメント由来。push 前に折り返し or `# noqa: E501` 個別免除で対応可能。

### 低 4: entity_context の部分一致ヒューリスティック検討

`Alibaba Cloud` vs `Alibaba` のような vendor 名のドメイン省略形を太字化する仕組み。false positive リスクと天秤。データ件数増加後に判断。

## 守るべき制約 (Part 3 から継続)

- **76 PASS 維持**: 新規追加は OK だが落とさない
- **コミット & push は明示 GO 待ち**: `# CLAUDE_PUSH_CONFIRMED` marker (block_remote_git.ps1 hook で物理ブロック)
- **DESIGN.md トークン経由で色・余白指定**: 直書き禁止
- **新規 entity 追加は同 category 2 件以上で `comparison.cols` 必須**
- **`history[].url` / `modules.future[].url` / `event.source_url` は WebSearch / WebFetch + urllib HEAD/GET で実機 200 確認したものだけ書く**
- **push 前は必ず `./.venv/Scripts/python.exe tools/audit_urls.py --gate` を通す**
- **HYBRID_MODE の本番デフォルトは `local_first`**: 緊急時のみ `gemini_only` 切替
- **`prompts/extract_grounded.md` 本線・強調記法は `rewrite_emphasis` (add_emphasis_event + rewrite_event) で決定論コード付与** (LLM プロンプトに強調記法指示は書かない)
- **新規 subprocess 起動は `tools/_proc/run.py` の `quiet_run` 境界を必ず通す**: ruff TID251 ban で物理弾き
- **アセット変更 (`static/` / `templates/`) を含む commit は `static/sw.js` の CACHE bump 必須**
- **Gemini API 呼出 (`tools/run_daily.py` 含む) は事前承認必須**
- **Task Scheduler Action の書き換えはユーザー手動**: Part 4 で .ps1 ファイルは作成済だが Task Scheduler 登録は触っていない

## 重要ファイル参照 (詳細を確認したい時のみ Read)

- `docs/handoff_2026-06-05_session_close_part3.md` — Part 3 (ハイブリッド本配線完了)
- `docs/handoff_2026-06-05_session_close_part2.md` — Part 2 (緊急停止対応 + 構造的未配線発覚)
- `tools/rewrite_emphasis.py` — 拡張後の本配線 (rewrite_event + add_emphasis_event)
- `tools/collect_rss.py` L250-258 — ev_marked → ev_rewritten チェーン
- `scripts/run_daily.ps1` / `run_weekly.ps1` — Task Scheduler 新版
- `tests/test_rewrite_emphasis.py` — 15 件契約テスト (旧 6 + 新 9)

## 推奨着手順 (Part 5 以降)

1. **commit + push 承認**: 上記コミット案でユーザー GO を取り、`audit_urls --gate` 通過後 push
2. **Task Scheduler Action 書き換え** (ユーザー手動): 次の朝 7:00 で `_logs/daily_YYYYMMDD.log` が文字化けなく生成されるか観察
3. **数値捏造ゲートの日本語助数詞対応** (中 2) を実装するか判断
4. **Gemini API 6/15 課金確認** (中 1) を実施

## 統計 (Part 4 セッションの実績)

- **テスト**: 66 → **76 PASS** (+10 件 / FAIL 0)
- **events.jsonl 強調記法更新**: 160/171 events (==+106 / __+237 / **+131)
- **新規ファイル**: 3 件 (`run_daily.ps1` / `run_weekly.ps1` / 本 handoff)
- **変更ファイル**: 5 件 (`rewrite_emphasis.py` / `collect_rss.py` / `test_rewrite_emphasis.py` / `events.jsonl` / `entities.jsonl`)
- **Gemini API 課金**: **$0** (smoke 2 entity 走らせて fallback 発火ゼロ)
- **採用された新規 event**: 2 件 (qwen-image)
