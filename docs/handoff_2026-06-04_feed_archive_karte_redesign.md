# 次セッション引継ぎ — フィード/アーカイブ/カルテ役割分離 + flash-lite 切替

作成: 2026-06-04
前提セッション: フル収集完了 (107 events / 21 karte / 23 ページ) + E2E 検証 PASS。詳細は本日コミット前の `git status` で確認可。

## 1. ユーザー指示（本セッション中の割り込みで明示・原文ベース）

> 現在ある「フィード」「アーカイブ」の差を明らかにしたい。現在「フィード」も「アーカイブ」も本質的に表現している情報が一緒です。
> 「アーカイブ」がタイムラインならば、「フィード」はより情報を濃くすべきです。サムネイルとフォントサイズは一回り大きくし、説明文の長さも 2 倍は欲しいです。
> 「アーカイブ」ですが、ニュースタイトルだけでなく、一行でまとめた説明文と関連するカルテ名がないと英語タイトルだけの場合もあり内容が分かり辛いです。
> また、「関連カルテ」ではなく、実際に関連するカルテ名をそのまま張り付けるべきでしょう。複数個対応もできるように。
> あとメニューには「フィード」と「アーカイブ」以外に「カルテ」を足して、カルテページでは分野ごとのカルテの一覧がカード形式であるべきでしょう。そこには最低限の情報を載せるようにしてください。
> 過去分全部含んでいるので、当日分だけ表示

## 2. 確定要件（次セッションで実装）

### 2.1 フィード（index.html）

- **表示対象を「当日分のみ」に絞り込む**（現状は全 107 件無条件表示）
- 情報密度を上げる：
  - **サムネイル**を一回り大きく
  - **フォントサイズ**を一回り大きく
  - **summary**（現状は `<li.story> > .body` 配下の説明）を **約 2 倍の長さ**にする
- 関連カルテ表示は実カルテ名で（2.3 と同じ）

### 2.2 アーカイブ（archive.html）

- 現状はタイムライン形式だが「ニュースタイトルだけ」で英文だと内容不明
- 各 entry に以下を追加：
  - **1 行サマリ**（短文）
  - **関連カルテ名** を実名で表示（複数対応）

### 2.3 「関連カルテ」表記の廃止

- 「関連カルテを見る」などの抽象ラベルをやめ、**実際のカルテ名**（例: `Claude Opus`, `Devin`）を直接表示
- **複数カルテ対応**：1 つの記事が複数 entity に紐づく場合、すべて並べる
- データソース: events.jsonl の `entity_id` が現状 1 値。複数 entity 対応にはスキーマ拡張も検討（`entity_ids: list[str]` への移行 or 既存単数のまま entity_id を分割不可とするか）

### 2.4 「カルテ」メニュー新設

- 既存メニュー（「フィード」「アーカイブ」）に **「カルテ」** を追加
- カルテ一覧ページの仕様：
  - **分野（category）ごとに分類**
  - **カード形式**で各カルテを並べる
  - 各カードには **最低限の情報のみ**（カルテ名 / 1 行 positioning / カテゴリバッジ / カルテへのリンク）
- 配置場所候補: `site/karte-index.html`（仮称）

## 3. 設計上の検討課題

### 3.1 entity_id を複数対応にする場合の波及範囲

現状 schema は `entity_id: str`（単一）。複数対応するには：

| パス | 影響箇所 | 工数感 |
| --- | --- | --- |
| A) スキーマ変更 (`entity_id` → `entity_ids: list[str]`) | tools/schema.py / tools/store.py の dedup キー / tools/generate_pages.py / 既存 jsonl のマイグレーション / 契約テスト全件 | 大 |
| B) 主 entity_id 単一 + 補助フィールド (`related_entities: list[str]` 追加) | schema.py に optional field 追加 / generate_pages.py のレンダリング側で利用 / 既存 jsonl は触らず | 中 |
| C) Gemini プロンプトで本文から関連 entity を抽出 | prompts/gemini_summarize.md 改修 / 既存 76 件は再処理しない（または別バッチ実行） | 中 |

**推奨**: B（補助フィールド追加）。既存データを守りつつ将来拡張可。

### 3.2 「当日分のみ」の判定基準

- `date` フィールド（記事 pubDate）か？ それとも `karte_updated` 時刻か？
- 今日の日付（JST）を取って `ev['date'] == today_jst.isoformat()` でフィルタするのが最も直感的
- ただし収集が遅延した場合、当日の記事が翌日のフィードに出てしまう問題あり
- 解決案: `date` は記事日付として残し、別途 `ingested_at` を追加し当日 ingest 分を表示する

### 3.3 「情報を 2 倍」の具体パラメータ

- 現状 summary は ~100 字程度（gemini-2.5-flash 出力）
- 2 倍 = ~200 字を目標
- 案 1: Gemini プロンプトで「summary は 150-250 字で書け」と指示
- 案 2: 既存 summary はそのまま、新フィールド `summary_long` を追加して使い分け
- 案 1 が単純。案 2 は破壊的でないが冗長

## 4. flash-lite 切替（並行実施推奨）

詳細: [docs/eval/2026-06-04_flash_vs_flash_lite.md](./eval/2026-06-04_flash_vs_flash_lite.md)

### 結論（4 件サンプル分析）

- 品質差: summary が ~1.4 倍長い・rationale が ~30% 長い程度。実用上許容範囲
- score: flash-lite が ~5pt 低めだが SCORE_MIN=50 なので採用率に影響なし
- event_type 分類: 4/4 完全一致
- **コスト 6 倍以上安い**（output が $2.50/1M → $0.40/1M）
- **無料運用が可能**（Free Tier RPD は flash 20 → flash-lite は 1000 級と想定。要 AI Studio dashboard 実測確認）

### 切替手順

1. `tools/config.py`:
   - `GEMINI_MODEL = "gemini-2.5-flash-lite"`
   - `GEMINI_RPM = 8` → `15`（flash-lite の Free Tier RPM）
2. AI Studio dashboard で実際の RPD 上限を確認（公式 docs は 2026-05-28 以降数値非掲載）
3. 1 entity (devin) でテスト → フル収集 → samples 確認
4. 1 週間運用後の採用率を観察（顕著低下なければ確定）

### 注意点（要件 2.1 「summary 2 倍」との相互作用）

- flash-lite の summary は flash より短くなる傾向（実測 ~100 字 vs ~140 字）
- ユーザー要件「summary を 2 倍 = 200 字」を達成するには **プロンプト変更も同時に行う必要あり**
- 推奨: flash-lite 切替と同時に `prompts/gemini_summarize.md` で `summary` の文字数指示を強化

## 5. 次セッション着手順（推奨）

| 順 | タスク | 工数 | 影響範囲 |
| --- | --- | --- | --- |
| 1 | flash-lite 切替 + プロンプト summary 文字数強化 | 30 分 | config.py / prompts/gemini_summarize.md |
| 2 | 既存 events.jsonl の summary 再生成（任意） | 別バッチ | データ更新 |
| 3 | `entity_id` → 補助フィールド `related_entities` 追加 (案 B) | 1h | schema.py 拡張・互換維持 |
| 4 | フィードを「当日分のみ」+ 情報密度アップ | 1h | generate_pages.py（index 部分）/ CSS |
| 5 | アーカイブに 1 行サマリ + 実カルテ名を追加 | 30 分 | generate_pages.py（archive 部分） |
| 6 | カルテ一覧ページ新設（カード形式・分野別） | 1h | generate_pages.py 新セクション + 新テンプレート |
| 7 | E2E 再検証（desktop 1280 + mobile 390） | 30 分 | Chrome DevTools MCP |

合計: 約 4-5 時間

## 6. 守るべき制約（前セッションから継続）

- 既存 43 PASS を**一切いじらない**（不変条件保護）
- API キーを git に commit しない（`.env` は `.gitignore` 必須）
- コミットは明示 GO まで実施しない（`safe-commit` ゲート通過後）
- push は明示 GO 待ち（不可逆）
- スキーマ変更を伴う案は **必ず後方互換性を保つ**（既存 107 件を壊さない）

## 7. 関連 memory

- `project_ai_pulse`（プロジェクト現状）
- `feedback_research_constraints_upfront`（Gemini 制約は最初に明文化）
- `feedback_no_speculation`（公式 docs 数値非掲載問題、実測確認必須）
- `feedback_check_design_principles`（複数 entity 対応は schema 拡張 vs 補助フィールドで第 1〜2 段の選択）
- `feedback_test_before_report`（完了報告前に 43 PASS + 実測値）
- `feedback_web_ui_e2e_test`（Chrome DevTools E2E まで）

## 8. 本セッション完了状態（参考）

- フル収集: 76 件採用、events.jsonl 31 → 107
- pytest: 43 PASS
- site/: 23 ページ再生成済
- E2E: desktop 1280 + mobile 390 ともに 横はみ出し 0 / console error 0
- 比較スクリプト: `tools/eval_flash_vs_lite.py`（独立スクリプト・events.jsonl は触らない）
- 比較レポート: `docs/eval/2026-06-04_flash_vs_flash_lite.md`
- E2E スクリーンショット: `docs/e2e/2026-06-04_{desktop1280,mobile390}_{index,karte-claude-opus}.png`
- コミット: 未実施（ユーザー明示 GO 待ち）
