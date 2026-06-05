# Session Close — 2026-06-05 Part 6

## このセッションの位置づけ

Part 5 で完了した「新規 entry への `headline_ja` 自動付与 (collect_rss 統合)」(commit `8b82451` push 済) を受けて、Part 6 はハンドオフ末尾に「ユーザー意図変更時のみ実施」と保留されていた **スコープ B: 既存 entry への `headline_ja` 遡及付与** を実装・適用した。

ユーザー指示 (Part 6 冒頭):

> 現在存在する英語タイトルの翻訳をしてほしいですね。

Part 6 で commit 2 件 を作成し `origin/master` へ push 済。working tree は clean。

| commit | 内容 |
|---|---|
| (Commit 1) | Part 5 で未 commit のまま残っていた `docs/handoff_2026-06-05_session_close_part5.md` の清算追加 |
| (Commit 2) | スコープ B 本実装 (apply_headline_ja.py + 契約テスト + events.jsonl 一括翻訳 + 本 handoff) |

## Part 6 で完了したこと

### 1. 新規スクリプト `tools/apply_headline_ja.py` (汎用化)

handoff Part 5 に明記の「`tools/apply_headline_ja_2026_06_05.py` (Claude 直接翻訳の一回限り) を汎用化して `tools/apply_headline_ja.py` にリネーム or 新規ツール」を新規作成方向で実装。

**入出力**:
- 入力: `data/events.jsonl` 全件 (--data で差し替え可)
- 抽出: `collect_rss._needs_headline_ja` 再利用 (= ASCII≥0.95 かつ `headline_ja` 未付与)
- 翻訳経路: `llm_hybrid.translate_headline_ja` (Part 5 既設境界 1 関数 / HYBRID_MODE=local_first)
- 出力: `data/events.jsonl` 上書き (Part 5 の単純 write 方式踏襲)

**フラグ**:
- `--dry-run`: LLM を一切呼ばず件数とサンプル 10 件のみ表示 (Gemini API 課金リスクなし)
- `--limit N`: 先頭 N 件のみ翻訳 (テスト・段階適用用)
- `--data PATH`: events.jsonl パス上書き

**設計上の重要決定 (entity_context=None)**:

最初の `--limit 5` で実走したところ、`entity_id` を `entity_name` として `llm_hybrid.translate_headline_ja` に渡すと LLM が `entity_id` スラグを「公式な固有名詞表記」と誤解する事故が出た。

| event_id | 元 headline | 1 回目翻訳 (entity_context 付き) | 真因 |
|---|---|---|---|
| `2026-06-02-flux-gem03` | Martin Scorsese Supports AI Company, Using It to Storyboard Movies | マーティン・スコセッシ監督、AI企業**flux**を映画の絵コンテ制作に活用 | entity_id=`flux` を「会社名」として注釈混入 (= **翻訳の捏造**) |
| `2026-06-04-physical-gem04` | HKUST and CalmCar Establish the Physical AI Innovation Center, ... | HKUSTとCalmCar、Physical AIイノベーションセンター設立、**Physical-Intelligence**の新時代へ | entity_id=`physical-intelligence` のハイフン形式を「公式表記」として反映 |

恒久対策として `apply_headline_ja.py` は **entity_context=None** で `translate_headline_ja` を呼ぶ ([[feedback_check_design_principles]] §2 「境界 1 箇所集約」: 元 headline 本文だけを根拠に翻訳させる安全側)。

5 件再翻訳で flux 捏造ゼロ・Physical-Intelligence ハイフン化なしを実測確認した上で残り 59 件本実行。

### 2. 契約テスト `tests/test_apply_headline_ja.py` (4 件)

| テストクラス | 内容 |
|---|---|
| `TestScanTargets` | `_scan_targets` が「既 headline_ja / 日本語混在」を必ず除外する |
| `TestDryRunDoesNotCallLLM` | `--dry-run` は `translate_headline_ja` を 1 度も呼ばない (Gemini 課金事故ガード) |
| `TestLLMErrorIsSkippedNotFatal` | 途中 LLMError でも止まらず成功 entry は events.jsonl に書き込まれる |
| `TestEntityContextIsAlwaysNone` | `translate_headline_ja` は **必ず** `entity_context=None` で呼ばれる (flux 捏造逆行防止 / [[feedback_check_design_principles]] §4) |

### 3. 全 64 件の本実行と 1 件手動修正

| 工程 | 実測値 |
|---|---|
| 翻訳対象 (`_needs_headline_ja` 該当 + 未付与) | 64 件 |
| LLM 経路 | Ollama Qwen3.6-35B-A3B (GPU mem 3847 MB < 閾値 6000 MB のため local_first 維持) |
| Gemini API フォールバック発動 | 0 件 (= API 課金 **$0**) |
| 平均処理時間 | 1.0-1.8 s/件 (warm 後) |
| 成功 | 64/64 |
| 失敗 | 0/64 |

**カバレッジ**: events.jsonl 全 171 件中、ASCII≥0.95 の英語見出し **146 件すべてに `headline_ja` 付与** (Part 4 既訳 82 + 今回 64)。

**手動修正 1 件** (LLM の意味反転誤訳):

| event_id | EN | LLM 出力 | 手動修正 |
|---|---|---|---|
| `2026-04-20-qwenimag-gem03` | Alibaba Drops Qwen 3.6 Max Preview—Its Most Powerful Model Yet | Alibaba、最も強力なモデル Qwen 3.6 Max のプレビューを **中止** | Alibaba、これまでで最強モデル Qwen 3.6 Max のプレビューを **公開** |

"Drops" は文脈的に「投下/発表」が正解 (続く "—Its Most Powerful Model Yet" との整合性から判断)。これは entity_context 由来ではなく LLM の自然言語解釈の限界。

### 4. 字数分布の実測

| 指標 | 値 |
|---|---|
| min / max / avg | 4 / 86 / 38.2 字 |
| プロンプト目安 (30-50 字) 内 | ~50% |
| 50 字超 (上限超過) | 25 件 (39%) |
| 20 字未満 (短縮過剰) | 14 件 (22%) |

長過ぎ・短過ぎは「30〜50 字程度」という緩い表現のプロンプトを Qwen3.6 が幅広く解釈した結果。実害判明時のみ個別修正。

### 5. push 前ゲート

| ゲート | 結果 |
|---|---|
| `pytest --ignore=tests/test_urls_live.py` | **89 PASS / 0 FAIL** (前回 85 → +4) |
| `tools/audit_urls.py --gate` | **191/191 OK, 0 NG** |
| `block_remote_git.ps1` hook | `# CLAUDE_PUSH_CONFIRMED` marker 付与で通過 |

## 変更ファイル一覧

### Commit 1 (Part 5 漏れ清算)

```
A  docs/handoff_2026-06-05_session_close_part5.md   (Part 5 セッションで作成済だが commit 漏れ)
```

### Commit 2 (Part 6 本実装)

```
A  tools/apply_headline_ja.py                       (新規 / 汎用化スクリプト 約 130 行)
A  tests/test_apply_headline_ja.py                  (新規 / 契約テスト 4 件 約 130 行)
M  data/events.jsonl                                (64 entries に headline_ja 追加 + 1 件手動修正)
A  docs/handoff_2026-06-05_session_close_part6.md   (本ファイル)
```

## 既知の挙動 (ユーザー合意済み)

### 字数 50 字超 25 件 / 20 字未満 14 件は許容

プロンプト「30〜50 字程度」を Qwen3.6 が緩く解釈した結果。実害判明時のみ個別修正の方針 (Part 6 確定)。

### 潜在的な意訳ミス可能性は残る

`qwenimag-gem03` の "Drops" のような語彙反転誤訳は他にも残っている可能性がある (全 64 件抜き取り確認は未実施)。手動レビューはユーザー判断で随時。

### Physical Intelligence は「概念」として和訳

`physical-gem04` / `physical-gem05` で `Physical Intelligence` を「物理知能」「物理インテリジェンス」と和訳。文脈上は概念扱いで妥当だが、Physical Intelligence Inc. (pi.ai) という会社名を指す entry が将来混入したら誤訳になる可能性あり。

## 残タスク (Part 5 から継続 + Part 6 で発生したもの)

### Part 5 残タスクの状態棚卸し

| Part 5 残タスク | Part 6 終了時の状態 |
|---|---|
| 🟡 P1 次の朝 7:00 Task Scheduler 起動観察 | ⏳ 未実施 (明日朝 7:00 待ち) |
| 🟢 P2 既存 entry への headline_ja 遡及付与 (スコープ B) | ✅ Part 6 で完了 |
| 🟢 P2 翻訳品質の事後監査 | ⏳ 未実施 (qwenimag-gem03 で 1 件発覚→個別修正済) |
| 🔵 P3 翻訳プロンプトの A/B 評価 | ⏳ 未実施 |
| 🟢 P2 既存 E501 (`llm_gemini.py` 等) | ⏳ Part 5 から継続 |
| 🟢 P2 数値捏造ゲートの日本語助数詞対応 | ⏳ Part 4 から継続 |
| 🟢 P2 `project_ai_pulse.md` の dispatch 自動 inject 化 | ⏳ Part 4 から継続 |
| 🟢 P2 entity_context の部分一致ヒューリスティック | ⏳ Part 4 から継続 (Part 6 で entity_context 自体の渡し方が「常に None」に固定されたため、本タスクは設計見直し必要) |

### Part 6 で新規発生した残タスク

| # | 優先 | タスク | 備考 |
|---|---|---|---|
| 1 | 🟡 P1 | 次の朝 7:00 Task Scheduler 起動観察 (Part 5 から継承 + Part 6 で apply_headline_ja の影響範囲は無いことを確認) | `_logs/daily_YYYYMMDD.log` 文字化けなし / 新規 entry に headline_ja 付与 / 翻訳品質 3 条件 |
| 2 | 🟢 P2 | LLM 意味反転誤訳の全件監査 (qwenimag-gem03 で 1 件発覚済) | 全 64 件の EN/JA 並記レビュー → 怪しい候補だけサンプリング翻訳 vs Claude 直接翻訳の差分判定 |
| 3 | 🟢 P2 | apply_headline_ja の冪等性向上 | 現状 LLM 失敗時は warn のみで部分 commit。再実行で取りこぼし回収 (`_needs_headline_ja=True` かつ未付与) は自然に動くが、ロールバック手段なし |
| 4 | 🔵 P3 | 字数制約の硬化 | 「30〜50 字」プロンプトに対し 50 字超 25 件 / 20 字未満 14 件。プロンプトに max_chars 明記 or 後段クランプを検討 |
| 5 | 🔵 P3 | collect_rss 側の entity_context 渡し方の見直し | Part 5 の collect_rss は `translate_headline_ja` に entity_context を渡している ([_make_event](../tools/collect_rss.py) で `entity` dict をそのまま渡す)。Part 6 で「entity_context は捏造源」と判明したので、collect_rss 側も None に揃えるか検討 |

## 守るべき制約 (Part 5 から継承 + Part 6 追加)

- **89 PASS 維持** (Part 5 で 85 → Part 6 で 89)
- **commit & push は明示 GO 待ち**: `# CLAUDE_PUSH_CONFIRMED` marker
- **DESIGN.md トークン経由で色・余白指定**: 直書き禁止
- **`history[].url` / `modules.future[].url` / `event.source_url` は実機 200 確認したものだけ書く**
- **push 前は必ず `./.venv/Scripts/python.exe tools/audit_urls.py --gate`**
- **HYBRID_MODE の本番デフォルトは `local_first`**
- **headline_ja の自動付与は `llm_hybrid.translate_headline_ja` が単一境界**
- **新規 subprocess 起動は `tools/_proc/run.py` の `quiet_run` 境界を必ず通す**
- **アセット変更 (`static/` / `templates/`) を含む commit は `static/sw.js` の CACHE bump 必須** (Part 6 では該当変更なし)
- **Gemini API 呼出は事前承認必須** (Part 6 では発動ゼロ確認)
- **apply_headline_ja は `entity_context=None` で `translate_headline_ja` を呼ぶ** (Part 6 追加 / 契約テスト `TestEntityContextIsAlwaysNone` で locked-in)

## 重要ファイル参照 (詳細を確認したい時のみ Read)

- [docs/handoff_2026-06-05_session_close_part5.md](handoff_2026-06-05_session_close_part5.md) — Part 5 (新規 entry への headline_ja 自動付与)
- [docs/handoff_2026-06-05_session_close_part4.md](handoff_2026-06-05_session_close_part4.md) — Part 4 (ハイブリッド + add_emphasis_event + .ps1 化)
- [tools/apply_headline_ja.py](../tools/apply_headline_ja.py) — Part 6 新規 / 汎用化スクリプト
- [tests/test_apply_headline_ja.py](../tests/test_apply_headline_ja.py) — Part 6 新規 / 契約テスト 4 件
- [tools/apply_headline_ja_2026_06_05.py](../tools/apply_headline_ja_2026_06_05.py) — Part 4 一回限り版 (82 件 TRANS dict) / 汎用化のベース資料として残置
- [tools/llm_hybrid.py](../tools/llm_hybrid.py) — `translate_headline_ja` 境界関数
- [tools/collect_rss.py](../tools/collect_rss.py) — `_needs_headline_ja` / `_ascii_ratio` / `_HEADLINE_JA_ASCII_THRESHOLD`

## 推奨着手順 (Part 7 以降)

1. **次の朝 7:00 Task Scheduler 起動観察** (Part 5 P1 + Part 6 P1 統合):
   - `_logs/daily_20260606.log` が UTF-8 文字化けなし
   - `grep '"headline_ja"' AI-Pulse/data/events.jsonl | wc -l` が朝 7:00 前後で増えるか
   - 翻訳品質 3 条件 (30-50 字 / 固有名詞英語維持 / 装飾記号なし) を実 entry で確認
2. **LLM 意味反転誤訳の全件監査**: qwenimag-gem03 で 1 件発覚済。今回 64 件分の EN/JA 並記を Claude が再レビューして怪しい候補を抽出
3. **collect_rss の entity_context 設計見直し** (Part 6 残 5): Part 5 の collect_rss は entity_context を渡しているが、Part 6 で「entity_context は捏造源」と判明。collect_rss 側も None に揃えるか、entity_context のキーを `entity_id` (内部スラグ) から「読みやすい正式名」に置き換えるかの設計判断

## 統計 (Part 6 セッションの実績)

- **テスト**: 85 → **89 PASS** (+4 件 / FAIL 0)
- **headline_ja カバレッジ**: 82/146 (56%) → **146/146 (100%)**
- **新規ファイル**: 3 (`tools/apply_headline_ja.py` / `tests/test_apply_headline_ja.py` / 本 handoff)
- **変更ファイル**: 1 (`data/events.jsonl` / 64 entries + 1 件手動修正)
- **Gemini API 課金**: **$0** (Ollama Qwen3.6 で全 64 件処理 / GPU 占有閾値未満で local_first 維持)
- **URL 偽造**: 191/191 OK (audit_urls --gate)
- **commit**: 2 件 (Commit 1: handoff_part5 清算 / Commit 2: Part 6 本実装)

## 引き継ぎ用プロンプト (次セッション冒頭で投げる用)

```
Part 6 で apply_headline_ja.py (汎用化) + 契約テスト 4 件 + events.jsonl 全件翻訳
を origin/master に push 完了。89/89 PASS / URL 191/191 OK / working tree clean。
headline_ja カバレッジ 100% (146/146)。

次は AI-Pulse/docs/handoff_2026-06-05_session_close_part6.md を読んで残タスクを
整理してください。優先順は「推奨着手順 (Part 7 以降)」セクション参照。

特に高優先は:
- 次の朝 7:00 Task Scheduler 起動観察 (Part 5 + Part 6 統合)

ユーザーから「他にも誤訳がないか確認したい」と指示があったら、Part 6 残 #2
(LLM 意味反転誤訳の全件監査) を実施してください。
```
