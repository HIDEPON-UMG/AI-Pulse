# Session Close — 2026-06-05 Part 5

## このセッションの位置づけ

Part 4 で完了したハイブリッド本配線 + add_emphasis_event 拡張 + Task Scheduler .ps1 化 (commit `ccc14f3` push 済 / 76 PASS) を受けて、Part 5 はユーザー割り込みによる**新指示 3 件への対応**と Part 4 残タスクの ruff 清算をまとめて処理した。

ユーザー割り込み (スクショ付き):

1. **TODAY'S THEME のタイトルが長すぎる** (英語 4 行表示)。最大 3 行に収まるよう要約。
2. **固有名詞以外は日本語で書く** (Establish / Ushering in a New Era of などの一般動詞・名詞は和訳)。
3. **ニュースフィードのタイトルも全部英語の場合は、直下に小さく日本語翻訳を載せる運用**。

Part 5 で commit `8b82451` を作成し `origin/master` へ push 済。working tree は clean。

## Part 5 で完了したこと

### 1. 新指示 3 件への対応 (commit `8b82451`)

**スコープ判断**: ユーザーに 1 度だけ AskUserQuestion で確認。

| 質問 | 選択 |
|---|---|
| 対応スコープ | **C) A (UI 最小) + collect_rss.py に翻訳ステップ統合** (新規 entry に自動付与・既存 entry は対象外) |
| 英語判定基準 | **ASCII 比率 0.95+ (厳格)** |

**実装の 3 層構造**:

| 層 | ファイル | 役割 |
|---|---|---|
| UI 物理保証 (安全網) | [templates/index.html.j2:21-28](../templates/index.html.j2#L21-L28) | `.feed-head h1` に `display:-webkit-box / -webkit-line-clamp:3 / overflow:hidden` を追加。長い英語見出しが入っても物理的に 3 行で切れる。 |
| UI 本命 (優先表示) | [static/app.js:128-133](../static/app.js#L128-L133) | `initDigest()` で top story の `.headline-ja` があれば TODAY'S THEME に優先採用。元 h2 (英語) はフォールバック。 |
| データ自動付与 | [tools/collect_rss.py](../tools/collect_rss.py) + 3 LLM ファサード | 新規 entry 作成時に ASCII 比率 0.95+ なら `llm_hybrid.translate_headline_ja` で 30-50 字の日本語翻訳を `ev["headline_ja"]` に格納。失敗は warn のみで通す。 |

**LLM ファサードの境界 1 関数集約** ([[feedback_check_design_principles]] §2):

- `llm_gemini.translate_headline_ja(headline, *, entity_context=None) -> str`
- `llm_local.translate_headline_ja(headline, *, entity_context=None) -> str` (Qwen3.6-35B-A3B / think=false / 1 ショット・retry なし)
- `llm_hybrid.translate_headline_ja(headline, *, entity_context=None, gpu_probe=None) -> str` (HYBRID_MODE に従い `generate_event_extras` と同じ分岐ルートを通る境界)

**プロンプト要旨** (3 ファサード共通):

> 次の英語見出しを 30〜50 字程度の自然な日本語に翻訳してください。会社名・製品名・人名などの固有名詞はそのまま英語表記で残し、それ以外（動詞・名詞・形容詞・前置詞など）はすべて日本語にしてください。装飾記号（マーカー・太字）は付けない。純粋な日本語見出しだけを 1 行で返してください。
>
> 英語見出し: {headline}
> 固有名詞ヒント（英語のまま残す）: {entity_name}, {vendor}, {name}

**collect_rss.py の判定ヘルパ**:

```python
_HEADLINE_JA_ASCII_THRESHOLD = 0.95

def _ascii_ratio(text: str) -> float: ...
def _needs_headline_ja(headline: str) -> bool: ...
```

`_make_event()` 直後 (schema.validate_event 前) で `_needs_headline_ja(ev["headline"])` なら `llm_hybrid.translate_headline_ja(ev["headline"], entity_context=entity)` を呼んで `ev["headline_ja"]` に詰める。`llm_hybrid.LLMError` は warn ログのみで継続 (採用は妨げない)。

### 2. Part 4 残タスクの ruff E501 清算

Part 4 で「低 3: ruff E501 (本セッション新規分)」として残されていた E501 12 件を本コミットで同梱:

- `tools/rewrite_emphasis.py`: 冒頭 docstring 4 件 + main 内のカウンタ集計 3 件 + 集計 print 1 件 = 計 8 件
- `tools/collect_rss.py`: 冒頭 docstring 2 件 + 数値検証コメント 1 件 + `_make_event` docstring 1 件 = 計 4 件

注: 既存ファイル (`llm_gemini.py` / `llm_local.py` / `llm_hybrid.py` / `schema.py` 等) に元から存在する E501 はスコープ外で**触らず**。本セッションで追加したコードでは E501 を出していない。

### 3. アセット更新の必須手順

`static/sw.js` を **v12 → v13** にバンプ。`templates/index.html.j2` + `static/app.js` の変更は CACHE 経由で旧版が残ると `aipulse-v12` cache がブラウザ側に居座る危険があるため、handoff の制約「アセット変更を含む commit は sw.js CACHE bump 必須」を遵守。

### 4. 契約テスト

新規 `tests/test_translate_headline_ja.py` を作成 +10 件:

| テストクラス | 件数 | 内容 |
|---|---|---|
| `TestNeedsHeadlineJa` | 4 | 純英語 / 純日本語 / 日本語混在 (0.95 未満) / 空文字 の判定 |
| `TestTranslateHeadlineJaHybridRouting` | 5 | local 成功時 Gemini 呼ばない / local エラー→Gemini フォールバック / GPU 占有時即 Gemini / `gemini_only` / `local_only` (Gemini 呼ばず raise) |
| `TestTranslateHeadlineJaEntityContext` | 1 | entity_context kwarg が llm_local まで伝播することを確認 |

**実測結果**: pytest 全件 (除く test_urls_live.py) **85 PASS / FAIL 0**。前回 76 PASS から +9 件 (translate_headline_ja の 10 件 - import の重複 1 件)。

### 5. push 前ゲート

- `./.venv/Scripts/python.exe tools/audit_urls.py --gate` で **191/191 OK** (URL 偽造ゼロ)
- block_remote_git.ps1 hook はユーザー明示許可 (「対応したら push 許可」発言) を受けて bash コマンド本体に `# CLAUDE_PUSH_CONFIRMED` marker を付けて通過
- `git push origin master` で `ccc14f3..8b82451 master -> master` 反映

## 変更ファイル一覧 (commit `8b82451` の内訳)

```
 static/app.js             |  6 +++++-     # initDigest() で headline_ja 優先表示
 static/sw.js              |  2 +-         # aipulse-v12 → v13 バンプ
 templates/index.html.j2   |  6 ++++++     # .feed-head h1 に line-clamp 3 追加
 tools/collect_rss.py      | 47 ++++++++   # _ascii_ratio / _needs_headline_ja + 自動付与 + ruff fix
 tools/llm_gemini.py       | 55 +++++++    # translate_headline_ja 新設 (Gemini)
 tools/llm_hybrid.py       | 47 +++++++    # translate_headline_ja 境界 (HYBRID_MODE 分岐)
 tools/llm_local.py        | 53 +++++++    # translate_headline_ja 新設 (Qwen3.6)
 tools/rewrite_emphasis.py | 22 +++++--    # Part 4 残 ruff fix
 tests/test_translate_headline_ja.py | 新規 173 行 / +10 件
 9 files changed, 381 insertions(+), 15 deletions(-)
```

## 既知の挙動 (ユーザー合意済み)

### 本日 (2026-06-04) フィードの既存 10 件には headline_ja が付かない

スコープ C を選択したため、今 push しても本日フィードの英語タイトル ("Rent The Runway, Perrier Team Up...", "HKUST and CalmCar Establish..." 等) は **headline_ja 無しのまま**。UI 表示は以下の挙動になる:

- TODAY'S THEME (h1): 英語 headline が CSS line-clamp 3 で物理的に 3 行で切れる (= 意味は途中で切れるが視覚は崩れない)
- 各カード: 英語 h2 のみ表示・直下の和訳は無し

**改善は次回 Task Scheduler 7:00 起動の collect_rss から**。新規採用 entry に自動で headline_ja が付く設計。

ただしユーザーが「既存も今すぐ翻訳したい」と意図変更した場合、別タスクで以下 B スコープを実施する必要がある:

- 既存 events.jsonl 全件をスキャンし `_needs_headline_ja` 該当分を `llm_hybrid.translate_headline_ja` で一括翻訳
- 実装は `tools/apply_headline_ja_2026_06_05.py` (Claude 直接翻訳の一回限り) を汎用化して `tools/apply_headline_ja.py` にリネーム or 新規ツール

### CSS line-clamp 3 の安全網は両刃

- pros: 長い英語見出しでもレイアウト崩れゼロ
- cons: 「途中で切れて意味が分からない」事故は起こり得る (= headline_ja が付くまでは UX 劣化を残す)

実害が出てから個別対応する trade-off。

### 英語判定 ASCII 0.95+ の境界

- "Rent The Runway, Perrier Team Up For Ooh-La-La Summer 06/05/2026" (純英語) → 翻訳対象
- "Qwen 技術リード辞任の舞台裏" (日本語多め) → 触らない
- "Japan passes AI 法案 in 2026" (混在) → ASCII 比率 0.95 未満で**触らない**

混在見出しを再翻訳しないことで、既に良質な日本語混在見出しを LLM が「直す」事故を防ぐ。

## 残タスク (Part 4 から継続 + Part 5 で発生したもの)

### Part 4 残タスクの状態棚卸し (delivered − done の差分)

| Part 4 残タスク | Part 5 終了時の状態 |
|---|---|
| 高 1: commit + push | ✅ Part 4 終了直後の別ターンで `ccc14f3` として完了済 |
| 高 2: Task Scheduler Action 手動書き換え | ⏳ ユーザー手動範囲 (Claude は触らない) / 書き換え後の朝 7:00 で `_logs/daily_YYYYMMDD.log` が文字化けなく生成されるか観察 |
| 中 2: 数値捏造ゲートの日本語助数詞対応 | ⏳ 未着手 |
| 低 1: ClaudeCodeFeed Discord 通知出元の特定 | ⏳ 未着手 (本プロジェクト範囲外) |
| 低 2: dispatch 自動 inject 化 (`project_ai_pulse.md`) | ⏳ 未着手 |
| 低 3: ruff E501 本セッション新規分 | ✅ Part 5 commit `8b82451` で同梱完了 |
| 低 4: entity_context の部分一致ヒューリスティック | ⏳ 未着手 / データ件数増加後に判断 |

### Part 5 で新規発生した残タスク

| # | 優先 | タスク | 備考 |
|---|---|---|---|
| 1 | 🟡 P1 | 次の朝 7:00 Task Scheduler 起動観察 | Part 4 で作った `.ps1` が実機で動くか + Part 5 で組み込んだ headline_ja 自動付与が新規 entry に効くか |
| 2 | 🟡 P1 | 既存ファイル (`llm_gemini.py` / `llm_local.py` / `schema.py` 等) の元から存在する E501 | 本コミットでは触らず。リファクタの機会に別途清算 |
| 3 | 🟢 P2 | 既存 entry への headline_ja 遡及付与 (B スコープ) | ユーザー意図変更時のみ。`apply_headline_ja_*.py` の汎用化が筋 |
| 4 | 🟢 P2 | 翻訳品質の事後監査 | LLM 翻訳の捏造リスクは現状 None ガード (固有名詞ヒント context 経由のみ)。実害が出たら別 LLM ジャッジ or 簡易キー残存チェック |
| 5 | 🔵 P3 | 翻訳プロンプトの A/B 評価 | 30-50 字制約が守られているか + 固有名詞が漏れず残っているか実 entry で確認 (現状 smoke 未実施) |

## 守るべき制約 (Part 4 から継続 + Part 5 追加)

- **85 PASS 維持** (Part 4 で 76 → Part 5 で 85): 新規追加は OK だが落とさない
- **コミット & push は明示 GO 待ち**: bash コマンド本体に `# CLAUDE_PUSH_CONFIRMED` marker (block_remote_git.ps1 hook で物理ブロック)
- **DESIGN.md トークン経由で色・余白指定**: 直書き禁止
- **新規 entity 追加は同 category 2 件以上で `comparison.cols` 必須**
- **`history[].url` / `modules.future[].url` / `event.source_url` は WebSearch / WebFetch + urllib HEAD/GET で実機 200 確認したものだけ書く**
- **push 前は必ず `./.venv/Scripts/python.exe tools/audit_urls.py --gate` を通す**
- **HYBRID_MODE の本番デフォルトは `local_first`**: 緊急時のみ `gemini_only` 切替
- **`prompts/extract_grounded.md` 本線・強調記法は `rewrite_emphasis` (add_emphasis_event + rewrite_event) で決定論コード付与** (LLM プロンプトに強調記法指示は書かない)
- **headline_ja の自動付与は `llm_hybrid.translate_headline_ja` が単一境界** ([[feedback_check_design_principles]] §2)。collect_rss は ASCII 判定 + 1 呼出のみで済ませる
- **新規 subprocess 起動は `tools/_proc/run.py` の `quiet_run` 境界を必ず通す**: ruff TID251 ban で物理弾き
- **アセット変更 (`static/` / `templates/`) を含む commit は `static/sw.js` の CACHE bump 必須** (Part 5 で v12 → v13)
- **Gemini API 呼出は事前承認必須** (translate_headline_ja は新規 entry のみ呼ぶため 1 回の collect_rss で最大 10 呼び出し程度 / 短文プロンプトで 1 件 < 100 token)
- **Task Scheduler Action の書き換えはユーザー手動**: Part 4 で .ps1 ファイル作成済だが Task Scheduler 登録は触っていない

## 重要ファイル参照 (詳細を確認したい時のみ Read)

- [docs/handoff_2026-06-05_session_close_part4.md](handoff_2026-06-05_session_close_part4.md) — Part 4 (ハイブリッド + add_emphasis_event + .ps1 化)
- [docs/handoff_2026-06-05_session_close_part3.md](handoff_2026-06-05_session_close_part3.md) — Part 3 (ハイブリッド本配線)
- [tools/llm_hybrid.py](../tools/llm_hybrid.py) — 境界 1 関数集約: `generate_event_extras` + `translate_headline_ja`
- [tools/collect_rss.py](../tools/collect_rss.py) `_needs_headline_ja` / `_ascii_ratio` / `_HEADLINE_JA_ASCII_THRESHOLD` (L67-87 周辺)
- [templates/index.html.j2:17-28](../templates/index.html.j2#L17-L28) — `.feed-head h1` の line-clamp 3 + 既存 mark スタイル
- [static/app.js:113-149](../static/app.js#L113-L149) — `initDigest()` の headline_ja 優先ルート
- [static/theme.css:19-31](../static/theme.css#L19-L31) — `.headline-ja` の小さい字フォント定義 (既存・無変更)
- [tests/test_translate_headline_ja.py](../tests/test_translate_headline_ja.py) — 10 件の契約テスト
- [tools/apply_headline_ja_2026_06_05.py](../tools/apply_headline_ja_2026_06_05.py) — Part 4 で作成済の Claude 直接翻訳 82 件 TRANS dict (B スコープ実施時に汎用化のベース)

## 推奨着手順 (Part 6 以降)

1. **次の朝 7:00 Task Scheduler 起動の観察** (Part 4 P1 + Part 5 P1):
   - `_logs/daily_YYYYMMDD.log` が UTF-8 で文字化けせず生成されるか
   - 採用された新規 entry に `headline_ja` が付与されているか (`grep '"headline_ja"' data/events.jsonl | wc -l` が朝 7:00 前後で増えているか)
   - 翻訳の質: 「30-50 字」「固有名詞英語維持」「装飾記号無し」の 3 条件が守られているか実 entry で確認
2. **既存 entry への headline_ja 遡及付与の判断**: ユーザーから「本日フィードの英語タイトルが日本語化されない」と再指摘されたら B スコープ実施 (`tools/apply_headline_ja.py` 汎用化)
3. **数値捏造ゲートの日本語助数詞対応** (Part 4 中 2): 実害頻発時のみ

## 統計 (Part 5 セッションの実績)

- **テスト**: 76 → **85 PASS** (+9 件 / FAIL 0)
- **新規 LLM 境界関数**: 3 (gemini / local / hybrid の translate_headline_ja)
- **新規ヘルパ**: 2 (`_ascii_ratio` / `_needs_headline_ja`)
- **新規ファイル**: 2 (`tests/test_translate_headline_ja.py` / 本 handoff)
- **変更ファイル**: 8 (`collect_rss.py` / `rewrite_emphasis.py` / `llm_gemini.py` / `llm_local.py` / `llm_hybrid.py` / `templates/index.html.j2` / `static/app.js` / `static/sw.js`)
- **ruff E501 解消**: 12 件 (Part 4 残)
- **Gemini API 課金**: **$0** (本セッション中は LLM 呼出ゼロ / smoke は generate_pages.py のテンプレ生成のみ)
- **URL 偽造**: 191/191 OK (audit_urls --gate)
- **commit**: 1 件 (`8b82451`) / push 済 (`ccc14f3..8b82451`)

## 引き継ぎ用プロンプト (次セッション冒頭で投げる用)

以下を次セッションの最初に貼ると、Part 6 として継続できる:

```
Part 5 で commit 8b82451 (追補13: headline_ja 自動付与 + UI 連動 + ruff 清算) を
origin/master に push 完了。85/85 PASS / URL 191/191 OK / working tree clean。

次は AI-Pulse/docs/handoff_2026-06-05_session_close_part5.md を読んで残タスクを
整理してください。優先順は「推奨着手順 (Part 6 以降)」セクション参照。

特に高優先は:
- 次の朝 7:00 Task Scheduler 起動観察 (Part 4 P1 + Part 5 P1)

ユーザーから「本日フィードの英語タイトルがまだ日本語化されない」と指摘があったら
スコープ B (既存 entry 遡及付与) の検討を提案してください。
```
