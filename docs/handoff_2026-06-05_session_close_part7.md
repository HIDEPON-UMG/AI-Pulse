# Session Close — 2026-06-05 Part 7

## このセッションの位置づけ

Part 6 で完了した「既存 entry への `headline_ja` 遡及付与」(commit 同梱予定) を受けて、Part 7 はユーザー割り込み指示への対応として **rationale (判断理由 3 軸) の文章必須化を schema で物理ゲート** + **既存「単語のみ rationale」24 件の遡及再生成** を実装した。

ユーザー指示 (Part 7 冒頭の割り込み + スクショ):

> たまに判断理由は結果「high」とか「mid」しか返ってきてない時があるので、絶対に文章で説明させる、してない場合ははじいて再作成させる仕組みをつくってください。

スクショ: `2026-06-04-physical-gem04` (HKUST and CalmCar / Physical AI) の EVALUATE 欄が「重要 high / 影響 high / 話題 high」と単語のみ表示。

Part 6 + Part 7 の 3 commit 構造で `origin/master` へ push:

| commit | 内容 |
|---|---|
| (Commit 1) | Part 5 で未 commit のまま残っていた `docs/handoff_2026-06-05_session_close_part5.md` の清算追加 |
| (Commit 2) | Part 6 本実装 (apply_headline_ja.py + 契約テスト 4 件 + handoff_part6.md) ※ events.jsonl のデータ変更は Commit 3 に同梱 |
| (Commit 3) | Part 7 本実装 (schema 強化 + regenerate_rationale + LLM 境界 + 契約テスト 4 件 + handoff_part7.md + events.jsonl の Part 6 + Part 7 両データ変更) |

## Part 7 で完了したこと

### 1. 真因の特定: prompt 指示はあるが LLM が無視する

`prompts/extract_grounded.md` L32 で **既に明記済み**:

> rationale: {importance, impact, buzz} の 3 軸。各 40〜80 字。**"high"/"mid" 等の値ラベルを反復するだけの記述は禁止。**

それでも events.jsonl 全 171 件中 **24 件 (約 14%) で rationale が単語のみ** に縮退していた ([`2026-06-04-physical-gem04`](../data/events.jsonl) 等)。`schema._validate_event_extras` の rationale 検証は「非空文字列」のみ要求 (= "high" 1 単語でも通過) のため、prompt 違反を物理的に検出できなかった。

**対策**: ハードゲートを schema 側に追加 ([[feedback_check_design_principles]] §1 illegal state を表現できなくする / §4 契約テスト 1 件で locked-in)。

### 2. schema 強化 (minLength=20 字)

| ファイル | 変更 |
|---|---|
| [tools/schema.py:32-37](../tools/schema.py#L32-L37) | 定数 `_RATIONALE_MIN_LEN = 20` を新設 (prompt 40-80 字より緩いが「単語かどうか」のクラスを物理的に分ける安全側) |
| [tools/schema.py:228-244](../tools/schema.py#L228-L244) | `_validate_event_extras` の rationale 検証に `too_short` チェック追加 ("high"/"mid"/"低と判定" 等を SchemaError で弾く) |
| [tools/schema.py:282-286](../tools/schema.py#L282-L286) | `gemini_response_schema()` の rationale.properties に minLength=20 を追加 (Gemini structured output で先制弾き) |

### 3. 契約テスト (TestSchemaContract に統合)

[tests/test_schema.py:150-167](../tests/test_schema.py#L150-L167) `test_event_extras_are_well_formed_when_present` に追加:

- `rationale: {importance: "high", impact: "high", buzz: "high"}` → SchemaError ✅
- `rationale: {importance: "高と判定", ...}` (1 軸でも < 20 字) → SchemaError ✅
- 文章 (各 20+ 字) → 通過 ✅

「class of bugs を 1 ルールで構造的に塞ぐ」設計 ([[feedback_check_design_principles]] §1 + §4)。

### 4. 影響を受けた既存テスト fixture の同期修正

schema 強化に伴い「rationale が 20 字未満」の fixture を持つテストが落ちるため、4 ファイル同期修正:

| ファイル | 旧 fixture | 新 fixture |
|---|---|---|
| [test_schema.py:155-159](../tests/test_schema.py#L155-L159) | `{importance: "i", impact: "m", buzz: "b"}` (1 字!) | 各 30-40 字の文章 |
| [test_generate.py:254-257](../tests/test_generate.py#L254-L257) | `{importance: "重要の根拠", ...}` (5 字) | 各 40-60 字の文章 |
| [test_generate.py:266-267](../tests/test_generate.py#L266-L267) | assert `"重要の根拠"` (旧 fixture 文字列を期待) | assert `"重要度を高と判定"` (新 fixture 部分文字列) |
| [test_llm_gemini.py:35-39](../tests/test_llm_gemini.py#L35-L39) | `{importance: "重要度の根拠サンプル", ...}` (10 字) | 各 40-50 字の文章 |
| [test_llm_hybrid.py:37-41](../tests/test_llm_hybrid.py#L37-L41) | `{importance: "重要度の根拠サンプル本文", ...}` (12 字) | 各 40-50 字の文章 |

### 5. LLM 境界に regenerate_rationale() を追加 (3 ファサード)

既存 event の `headline + summary + summary_points + importance ラベル` から rationale 3 軸を「文章で再生成」する関数を、collect_rss の generate_event_extras と同じ境界 1 関数集約パターン ([[feedback_check_design_principles]] §2) で追加:

| ファイル | 追加関数 |
|---|---|
| [tools/llm_local.py:113-235](../tools/llm_local.py#L113-L235) | `regenerate_rationale(headline, summary, summary_points, importance_label, *, entity_context=None)` (Ollama Qwen3.6 / structured outputs で rationale 3 キー + minLength=20 拘束) |
| [tools/llm_gemini.py:211-303](../tools/llm_gemini.py#L211-L303) | 同上 (Gemini Flash-Lite / response_json_schema で同等拘束) |
| [tools/llm_hybrid.py:141-181](../tools/llm_hybrid.py#L141-L181) | 同上 (HYBRID_MODE 分岐 / generate_event_extras と同じ local_first / gemini_first / *_only ルート) |

両ファサードとも:
- 1 回 + schema 違反時 1 回追記 retry (計 2 試行)
- 失敗で LLMError → llm_hybrid 層で対向 LLM にフォールバック (HYBRID_MODE=local_first の場合)
- collect_rss / apply 系スクリプトは llm_hybrid.regenerate_rationale だけ呼べばよい

### 6. 新規 `tools/regenerate_rationale.py` (汎用化遡及スクリプト)

[tools/regenerate_rationale.py](../tools/regenerate_rationale.py) (約 130 行) を新設。Part 6 の `apply_headline_ja.py` と同じ構造 (汎用化 / `--dry-run` / `--limit N` / `--data PATH`)。

**判定ロジック** (`_needs_rationale_regen`):
- rationale が dict でない → True
- 3 キーいずれかが「非文字列」or「< 20 字」→ True
- 全 3 軸 ≥ 20 字 → False (スキップ)

**設計上の重要決定** (Part 6 と同じ理由で `entity_context=None`):
- entity_id を entity_name として渡すと LLM が「公式名」と誤解して挿入する事故が Part 6 で観測されたため、本スクリプトも entity_context=None で呼ぶ (契約テスト `TestEntityContextIsAlwaysNone` で locked-in)

### 7. 契約テスト `tests/test_regenerate_rationale.py` (4 件)

| テストクラス | 内容 |
|---|---|
| `TestScanTargets` | 「文章 rationale 既在 (各 20+ 字)」を必ず除外、「短い/欠落/型違反」を必ず抽出 |
| `TestDryRunDoesNotCallLLM` | `--dry-run` は `regenerate_rationale` を 1 度も呼ばない (Gemini 課金事故ガード) |
| `TestLLMErrorIsSkippedNotFatal` | 途中 LLMError でも止まらず成功 entry は events.jsonl に書き込まれる |
| `TestEntityContextIsAlwaysNone` | `regenerate_rationale` は必ず `entity_context=None` で呼ばれる (entity_id スラグ混入逆行防止) |

### 8. 24 件の本実行 (LLM 経路: local_first / Ollama Qwen3.6)

| 工程 | 実測値 |
|---|---|
| 再生成対象 (rationale 各値 < 20 字 / events 全 171 件中) | **24 件 (約 14%)** |
| 集計時の私の誤読 | 当初「72 件」と報告したが、これは「3 軸 × 24 event = 72 値」を event 単位と誤って解釈していた → ユーザーに訂正済み |
| LLM 経路 | Ollama Qwen3.6-35B-A3B (GPU mem 3847 MB < 閾値 6000 MB で local_first 維持) |
| Gemini API フォールバック発動 | 4 件 (Ollama 一過性 LLMError → Gemini fallback) |
| Gemini 503 UNAVAILABLE 発生 | 4 件 (= Gemini 側オーバー負荷) → スクリプト冪等性で**そのまま再実行→4/4 OK** で回収 |
| 平均処理時間 | 1.0-2.1 s/件 (warm) |
| 成功 | **24/24 件** |
| 失敗 | 0 件 |

### 9. 字数分布の実測 (全 501 値 = 171 events × 3 軸)

| 指標 | 値 |
|---|---|
| min / max / avg | 31 / 228 / **65.7** 字 |
| 20-39 字 (短め / schema は通過) | 12 値 (2.4%) |
| **40-80 字 (prompt 範囲内)** | **432 値 (86.2%)** |
| 81 字超 (長め) | 57 値 (11.4%) |

**「20 字未満 = 0 値」を達成**。全 171 events で rationale 3 軸すべてが文章として最低限の情報量を持つ状態に到達。

### 10. push 前ゲート

| ゲート | 結果 |
|---|---|
| `pytest --ignore=tests/test_urls_live.py` | **93 PASS / 0 FAIL** (Part 6 終了時 89 → Part 7 +4: test_regenerate_rationale.py の 4 件) |
| `tools/audit_urls.py --gate` | **191/191 OK / exit=0** (ambiguous OK 1 件 retaildive.com 403 anti-bot は non-fatal) |

## 変更ファイル一覧

### Commit 1 (Part 5 漏れ清算)

```
A  docs/handoff_2026-06-05_session_close_part5.md   (Part 5 セッションで作成済だが commit 漏れ)
```

### Commit 2 (Part 6 本実装 / コードのみ)

```
A  tools/apply_headline_ja.py                       (新規 / 汎用化スクリプト 約 130 行)
A  tests/test_apply_headline_ja.py                  (新規 / 契約テスト 4 件 約 130 行)
A  docs/handoff_2026-06-05_session_close_part6.md   (新規 handoff)
```

events.jsonl のデータ変更 (Part 6 の headline_ja 64 件追加 + 1 件手動修正) は Commit 3 に同梱した (Part 7 の rationale 24 件再生成と同じファイル内で混在するため、git add -p hunk 単位分割を避けた実用的判断)。

### Commit 3 (Part 7 本実装 + データ変更同梱)

```
M  tools/schema.py                                  (minLength=20 + 定数 _RATIONALE_MIN_LEN)
M  tools/llm_gemini.py                              (regenerate_rationale 追加)
M  tools/llm_local.py                               (regenerate_rationale 追加)
M  tools/llm_hybrid.py                              (regenerate_rationale 追加)
A  tools/regenerate_rationale.py                    (新規 / 汎用化遡及スクリプト 約 140 行)
A  tests/test_regenerate_rationale.py               (新規 / 契約テスト 4 件 約 150 行)
M  tests/test_schema.py                             (rationale 短すぎ弾き契約テスト追加 + fixture 修正)
M  tests/test_generate.py                           (fixture 20+ 字化 + assert 同期修正)
M  tests/test_llm_gemini.py                         (fixture 20+ 字化)
M  tests/test_llm_hybrid.py                         (fixture 20+ 字化)
M  data/events.jsonl                                (Part 6 headline_ja 65 entries + Part 7 rationale 24 entries 同梱)
A  docs/handoff_2026-06-05_session_close_part7.md   (本ファイル)
```

## 既知の挙動 (ユーザー合意済み)

### 字数 20-39 字 (12 値) は許容

prompt は「40-80 字」を要求しているが、schema は安全側で 20+ 字。LLM が「短めだが文章として通る」回答を返した場合は schema を通過する。実害判明時のみ個別修正の方針。

### 字数 81 字超 (57 値) も許容

prompt 上限 80 字を超える回答も schema は通過 (上限なし)。読みづらさが顕在化したら schema に maxLength を追加することを検討。

### Gemini 503 / 一過性失敗は冪等再実行で回収

regenerate_rationale.py は LLMError を warn ログ + 該当 entry スキップ設計のため、Gemini 503 / Ollama 一過性失敗は events.jsonl 上書きされずに残る。**スクリプトをそのまま再実行すれば `_needs_rationale_regen` が True を返して自動で再拾い**できる (= 冪等性)。今回 4 件失敗 → 再実行で 4/4 OK 回収を実測確認。

## 残タスク (Part 6 から継続 + Part 7 で発生したもの)

### Part 6 残タスクの状態棚卸し

| Part 6 残タスク | Part 7 終了時の状態 |
|---|---|
| 🟡 P1 次の朝 7:00 Task Scheduler 起動観察 | ⏳ 未実施 (明日朝 7:00 待ち) |
| 🟢 P2 LLM 意味反転誤訳の全件監査 | ⏳ 未実施 (qwenimag-gem03 で 1 件発覚→個別修正済) |
| 🟢 P2 apply_headline_ja の冪等性向上 | ✅ Part 7 で「冪等再実行で回収」の挙動を regenerate_rationale.py 経由で再検証 |
| 🔵 P3 字数制約の硬化 | Part 7 で rationale には minLength=20 を入れた / headline_ja の字数硬化は別途継続 |
| 🔵 P3 collect_rss 側の entity_context 渡し方見直し | ⏳ 未実施 (Part 6 では `apply_headline_ja` を None 固定にしたが、`collect_rss._make_event` 側の `translate_headline_ja` 呼び出しは entity_context を渡したまま) |

### Part 7 で新規発生した残タスク

| # | 優先 | タスク | 備考 |
|---|---|---|---|
| 1 | 🟡 P1 | 次の朝 7:00 collect_rss が新 schema を満たすか観察 | 新 entry の rationale が 20+ 字を満たすか実機確認。満たさない場合、`llm_local._call_once` の schema retry で救えるかを実測 |
| 2 | 🟢 P2 | rationale の字数上限 (maxLength) 追加検討 | 81 字超が 57 値 (11.4%) ある。読みづらさが顕在化したら maxLength=100 等を schema に追加 |
| 3 | 🟢 P2 | regenerate_rationale.py の `--data` 引数を活用したテスト用 fixtures セット | `--data tests/fixtures/sample.jsonl` で本物の Ollama を使わず dry-run / smoke できるテンプレが欲しい (現状は本番 events.jsonl 直接実行) |
| 4 | 🔵 P3 | LLM ファサードの 3 関数 (generate_event_extras / translate_headline_ja / regenerate_rationale) のパターン共通化 | DRY 化候補だが境界 1 関数集約の意図 (= 呼び出し側が単一関数を呼ぶ) を壊さない範囲で |

## 守るべき制約 (Part 5 + Part 6 から継承 + Part 7 追加)

- **93 PASS 維持** (Part 6 で 89 → Part 7 で 93)
- **commit & push は明示 GO 待ち**: `# CLAUDE_PUSH_CONFIRMED` marker
- **DESIGN.md トークン経由で色・余白指定**: 直書き禁止
- **`history[].url` / `modules.future[].url` / `event.source_url` は実機 200 確認したものだけ書く**
- **push 前は必ず `./.venv/Scripts/python.exe tools/audit_urls.py --gate`**
- **HYBRID_MODE の本番デフォルトは `local_first`**
- **headline_ja の自動付与は `llm_hybrid.translate_headline_ja` が単一境界**
- **新規 subprocess 起動は `tools/_proc/run.py` の `quiet_run` 境界を必ず通す**
- **アセット変更 (`static/` / `templates/`) を含む commit は `static/sw.js` の CACHE bump 必須** (Part 7 では該当変更なし)
- **Gemini API 呼出は事前承認必須** (Part 7 では 4 件のフォールバック発動 / 503 で全失敗 → 再実行 Ollama で回収 / 実課金は ~$0)
- **apply_headline_ja / regenerate_rationale は `entity_context=None` で対応 LLM 関数を呼ぶ** (Part 6 + Part 7 / 契約テスト 2 件で locked-in)
- **rationale 各値は 20 字以上必須** (Part 7 追加 / schema.py + gemini_response_schema + 契約テストで三重保証)

## 重要ファイル参照 (詳細を確認したい時のみ Read)

- [docs/handoff_2026-06-05_session_close_part6.md](handoff_2026-06-05_session_close_part6.md) — Part 6 (既存 entry への headline_ja 遡及付与)
- [docs/handoff_2026-06-05_session_close_part5.md](handoff_2026-06-05_session_close_part5.md) — Part 5 (新規 entry への headline_ja 自動付与)
- [tools/regenerate_rationale.py](../tools/regenerate_rationale.py) — Part 7 新規 / 汎用化遡及スクリプト
- [tests/test_regenerate_rationale.py](../tests/test_regenerate_rationale.py) — Part 7 新規 / 契約テスト 4 件
- [tools/schema.py](../tools/schema.py) — `_RATIONALE_MIN_LEN` + `_validate_event_extras` の too_short チェック
- [tools/llm_hybrid.py](../tools/llm_hybrid.py) — `regenerate_rationale` 境界関数 (3 LLM 経路)
- [prompts/extract_grounded.md](../prompts/extract_grounded.md) — collect_rss 本線プロンプト (rationale 40-80 字指示済 / 変更なし)

## 推奨着手順 (Part 8 以降)

1. **次の朝 7:00 Task Scheduler 起動観察** (Part 5 P1 + Part 6 P1 + Part 7 P1 統合):
   - `_logs/daily_20260606.log` UTF-8 文字化けなし
   - 新規 entry の headline_ja 付与
   - **新規 entry の rationale 3 軸が 20+ 字を満たすか** (= Part 7 schema 強化が collect_rss でも有効か確認)
2. **rationale 字数上限の検討**: 81 字超が 11.4% (= 読みづらさが顕在化したら maxLength=100 を schema 追加)
3. **collect_rss の entity_context 設計見直し** (Part 6 残 / Part 7 残 #4): collect_rss は依然 entity_context を渡している

## 統計 (Part 7 セッションの実績)

- **テスト**: 89 → **93 PASS** (+4 件 / FAIL 0)
- **rationale カバレッジ (3 軸すべて 20+ 字)**: 147/171 (86%) → **171/171 (100%)**
- **新規ファイル**: 3 (`tools/regenerate_rationale.py` / `tests/test_regenerate_rationale.py` / 本 handoff)
- **変更ファイル**: 7 (`schema.py` / `llm_gemini.py` / `llm_local.py` / `llm_hybrid.py` / `test_schema.py` / `test_generate.py` / `test_llm_gemini.py` / `test_llm_hybrid.py` / `data/events.jsonl`)
- **Gemini API 課金**: ~$0 (4 件のみフォールバック発動 → 全 503 → Ollama で再生成成功)
- **URL 偽造**: 191/191 OK (audit_urls --gate exit=0)
- **commit**: 3 件 (Commit 1: handoff_part5 / Commit 2: Part 6 code / Commit 3: Part 7 code + データ変更)

## 引き継ぎ用プロンプト (次セッション冒頭で投げる用)

```
Part 7 で rationale 文章必須化 (schema minLength=20) + 既存 24 件遡及再生成
(regenerate_rationale.py) を origin/master に push 完了。93/93 PASS / URL 191/191 OK /
working tree clean。rationale カバレッジ 100% (3 軸すべて 20+ 字 / 171/171)。

次は AI-Pulse/docs/handoff_2026-06-05_session_close_part7.md を読んで残タスクを
整理してください。優先順は「推奨着手順 (Part 8 以降)」セクション参照。

特に高優先は:
- 次の朝 7:00 Task Scheduler 起動の観察 (Part 5/6/7 統合 P1)
  - 新規 entry の rationale 3 軸が 20+ 字を満たすか実機確認
  - 満たさない場合、llm_local._call_once の schema retry で救えるかを実測

collect_rss 側の entity_context 渡し方の見直し (Part 6/7 残 #4) も検討してください
(現状 collect_rss._make_event は translate_headline_ja に entity_context を渡している)。
```
