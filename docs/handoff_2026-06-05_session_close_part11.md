# Handoff 2026-06-05 session close — Part 11 (P1 #3: collect_rss の entity_context を None に統一)

Part 10 で残課題化していた P1 #3 (Part 6 由来) を片付けた小規模セッション。collect_rss の `translate_headline_ja` 呼出を `entity_context=None` に統一し、apply_headline_ja / regenerate_rationale と契約を揃えた。明朝 7:00 Task Scheduler 起動時に新規 entry の翻訳で同じクラスの捏造事故 (Part 6 flux 事例) が再混入するリスクを構造で封じた。

## 動機 (Part 6 から繰越し)

Part 6 で `apply_headline_ja.py` を全 64 件実走した際、`entity` dict を `entity_context` として渡すと LLM プロンプトに `固有名詞ヒント: <name>, <vendor>` が注入され、**headline 本文に登場していない entity 名まで翻訳結果に強制混入**される事故が観測された。

| event_id | EN headline | 事故時の翻訳 (entity_context 付き) |
|---|---|---|
| `2026-06-02-flux-gem03` | Martin Scorsese Supports AI Company, Using It to Storyboard Movies | マーティン・スコセッシ監督、AI企業**flux**を映画の絵コンテ制作に活用 |
| `2026-06-04-physical-gem04` | HKUST and CalmCar Establish the Physical AI Innovation Center, ... | HKUSTとCalmCar、Physical AIイノベーションセンター設立、**Physical-Intelligence**の新時代へ |

Part 6 ではこれを受けて apply_headline_ja を `entity_context=None` 固定とし、契約テスト `TestEntityContextIsAlwaysNone` で locked-in した。Part 7 で regenerate_rationale も同様に固定。しかし collect_rss だけは `entity_context=entity` のままで、**P0 (明朝 Task Scheduler) 起動時に同じ事故が再混入する状態**だった。

## 真因の精査 (Part 11 で明確化)

3 LLM ファサード (`llm_local` / `llm_gemini` / `llm_hybrid`) の `translate_headline_ja` のプロンプト合成箇所を読み直すと、entity_context から抽出されているキーは `entity_name` / `vendor` / `name` のみで、`entity_id` (スラグ) は直接プロンプトに入れていない。

entities.jsonl の実値:

| entity_id | entity_name | name | vendor |
|---|---|---|---|
| flux | (なし → None) | FLUX | Black Forest Labs |
| physical-intelligence | (なし → None) | Physical Intelligence | Physical Intelligence |
| anima-base | (なし → None) | Anima Base v1.0 | CircleStone Labs |

→ Part 6 で観測された「flux 注入」は **entity_id スラグ自体の漏洩ではなく、`name='FLUX'` ヒントを LLM が無関係な見出しにも過剰適用した**結果。スラグの綴り問題でなく、ヒント機構そのものが捏造源。よって `name` を「読みやすい正式名」に置換する案 (B) では真因を解消できず、entity_context を全廃する案 (A) が構造的に正しい。

## 完了内容

### 1. 1 行修正 (`tools/collect_rss.py:299-310`)

```python
# Before
ev["headline_ja"] = llm_hybrid.translate_headline_ja(
    ev["headline"], entity_context=entity
)

# After
# entity_context=None 固定。entity dict を渡すと LLM プロンプトに
# 「固有名詞ヒント: <name>, <vendor>」が注入され、headline に登場しない
# entity 名まで翻訳に強制注入される事故が出る (Part 6 flux 捏造事例)。
# apply_headline_ja / regenerate_rationale と契約を統一する
# ([[feedback_check_design_principles]] §2 境界 1 箇所集約)。
ev["headline_ja"] = llm_hybrid.translate_headline_ja(
    ev["headline"], entity_context=None
)
```

### 2. 静的契約テスト (新規 `tests/test_collect_rss_translate_context.py`)

collect_rss はランタイムに fetch_article / Ollama / Gemini / Google News RSS が絡みテストが重いため、**AST 直接検査の静的契約テスト**で locked-in した ([[feedback_check_design_principles]] §3 「静的検査 1 ルールで封じる」)。

| テスト | 内容 |
|---|---|
| `test_source_file_exists` | collect_rss.py の所在確認 |
| `test_translate_headline_ja_is_called_at_least_once` | 翻訳呼出が削除されていないことを担保 (削除なら本テスト撤去のシグナル) |
| `test_entity_context_is_always_none_literal` | 全 translate_headline_ja 呼出で entity_context が **None リテラル** 明示。kwarg 省略・他値はすべて FAIL |

ランタイムテスト (`apply_headline_ja` / `regenerate_rationale` の TestEntityContextIsAlwaysNone) と AST 静的テスト (本 Part) の二段構えで、3 経路すべて構造的に封じられた。

## テスト状況

- 全 105 テスト PASS (Part 10 時点 101 + 今回追加 3 + α)
- pytest 実行時間 32.79 秒
- URL ライブチェック (`test_urls_live`) も実走で PASS (`AI_PULSE_SKIP_URL_CHECK` 未設定)

## 残タスク (Part 10 から継承)

### P0 (最優先・Part 9/10 から継続)

**2026-06-06 朝 7:00 Task Scheduler 起動の観察**:

1. `AI-Pulse/_logs/daily_20260606.log` が UTF-8 文字化けなしで生成されているか
2. 新規採用 entry (events.jsonl 追記分) に `headline_ja` が自動付与されるか
3. **新規採用 entry の headline_ja に「見出しに無い entity 名の混入」が無いか** (Part 11 で塞いだ事故の再発確認)
4. 新規採用 entry の rationale 3 軸 (importance / impact / buzz) が 20 字以上を満たすか

### P1 (ユーザー指示時のみ・Part 6/7 残)

1. **LLM 意味反転誤訳の全件監査** (Part 6 残 #2 / `2026-04-20-qwenimag-gem03` の "Drops=中止" 1 件発覚済み・他に類似 64 件サンプリングレビュー要)
2. **rationale 字数上限 (maxLength) 追加検討** (Part 7 残 / 現状 `minLength=20` のみ schema 拘束済み・上限未設定)
3. ~~`collect_rss` の `entity_context` 渡し方統一~~ → **Part 11 で完了**

### P3 (継続オープン項目)

**AI-Pulse メイン主題 = 記事増加** (現 events 171 / entities 30 / physical 0)。
集約先: `docs/handoff_2026-06-03_articles_expansion.md` (ただし時点情報は古い。実測の 06-05 時点状態は Part 11 本書を参照)

## 守るべき制約 (Part 11 追加)

- **collect_rss / apply_headline_ja / regenerate_rationale の 3 経路すべてで、`translate_headline_ja` / `regenerate_rationale` を呼ぶときは `entity_context=None`** ([[feedback_check_design_principles]] §2 境界 1 箇所集約 / §3 静的検査 / §4 契約テスト 1 件で locked-in)
- collect_rss は AST 静的テスト、apply/regenerate はランタイムテストで担保

## 変更ファイル一覧 (Part 11)

| ファイル | 種別 | 行数差 |
|---|---|---|
| `tools/collect_rss.py` | 修正 | +6 / -1 (コメント付与込み) |
| `tests/test_collect_rss_translate_context.py` | 新規 | +75 |
| `docs/handoff_2026-06-05_session_close_part11.md` | 新規 (本書) | +N |

## コミット推奨単位

Part 11 は 1 commit に集約推奨:
- `tools/collect_rss.py` (実装本体)
- `tests/test_collect_rss_translate_context.py` (静的契約テスト)
- `docs/handoff_2026-06-05_session_close_part11.md` (本書)

`safe-commit` ゲート 1-6 通過想定。`static/` / `templates/` 変更なしのため `sw.js` CACHE bump 不要。push は明示指示時のみ。

## 次セッション引継ぎプロンプト (新セッション冒頭にコピペ可)

```
AI-Pulse セッション継続。前セッション (Part 11) の作業履歴と残課題は
docs/handoff_2026-06-05_session_close_part11.md に集約。

状態:
- 直前 commit: 346162e (Part 10 slide animation) ※ Part 11 はまだ uncommitted
- origin/master ahead 0 (Part 11 push 前なら 0)
- 全 105 テスト PASS

最優先 P0: 2026-06-06 朝 7:00 Task Scheduler 起動の観察 (Part 10 から継続)
- daily_20260606.log の生成・文字化け確認
- 新規 entry headline_ja の自動付与確認
- ★ Part 11 で塞いだ entity 名注入事故の再発がないか確認 (新規追加チェック項目)
- 新規 entry rationale 3 軸 20 字以上確認

handoff Part 11 を読んでから着手してください。
```
