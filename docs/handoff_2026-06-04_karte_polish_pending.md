# 次セッション引継ぎ — カルテページの細部 2 件

作成: 2026-06-04 (本セッション末)
前提コミット: `2ac02f0` (origin/master へ push 済) 直後の状態。本ファイルは未コミット。

## 1. 「将来シナリオ」の時間軸ラベル「近 / 中 / 遠」を 3 周り大 + 明朝 + グラデ

### 現状

- 該当 CSS: [templates/karte.html.j2:156](../templates/karte.html.j2#L156) `.future .step .h`
- 該当 HTML: [templates/karte.html.j2:362](../templates/karte.html.j2#L362) `<div class="h">{{ f.label }}</div>`
- 現状値: `font-family: var(--font-mono); font-size: var(--t-label) (12px); color: var(--cat); padding-top: 2px;`

### ユーザー要件

- フォントを **3 周り大きく**（一発で時間軸が分かる視認性）
- **明朝系** に変更（モノスペースが「ダサい」と指摘）
- 色に **グラデーション** をかける

### 設計案メモ（次セッションで検証）

- フォント: `var(--font-head)` (Noto Serif JP) / weight 700
- サイズ: 12px → **24-28px**（3 段 ≒ `var(--t-h2)` 相当）
- グラデ: `background: linear-gradient(135deg, var(--accent), var(--cat)); background-clip: text; -webkit-text-fill-color: transparent;`
- 縦位置調整: 行高が変わるので `align-items: start` → `center` も検討（[karte.html.j2:153](../templates/karte.html.j2#L153)）
- 影響範囲: `.future .step .h` 1 箇所のみ。検索で他用途なし確認済

### 完了条件

- 全 21 カルテ再生成後、modules.future がある entity の future セクション目視
- DESIGN.md lint errors=0
- 47 PASS 維持

## 2. カルテページ最下段に「関連ニュース」をフィードページ形式で

### ユーザー要件

- 各カルテページ（`karte-<entity_id>.html`）の **最下段** に、その entity に紐づく events を **フィードページ（index.html）と同じレイアウト** で出す
- 表示範囲: **そのカルテに紐づく events 全件（新しい順）** ← AskUserQuestion で確定
  - SCORE_MIN フィルタは外す（カルテはアーカイブ的役割もある）
  - `entity_id` 一致 + `related_entities` に含まれるイベントも対象

### 設計案メモ

- データ: `build_context` 内で各 karte に `feed_items: list[story]` を渡す
  - 既存の `_story(ev, ent_by_id, ref, feature=False)` を再利用してフィードと同じ表現に
  - フィルタ: `ev["entity_id"] == ent["entity_id"] or ent["entity_id"] in (ev.get("related_entities") or [])`
  - 並び: 新しい順（`all_events` は既に新しい順ソート済なのでそのまま filter）
  - feature 化はしない（最下段の通常リスト扱い）
- テンプレ: [templates/karte.html.j2](../templates/karte.html.j2) 末尾 `</main>` 直前に `<section class="sect"><h2>関連ニュース</h2> <ul class="feed">...</ul></section>` を追加
- CSS: index.html.j2 の `.feed` / `.story` 系を `theme.css` か karte.html.j2 の `<style>` にコピー（共通化候補）
  - **共通化したいなら theme.css に切り出す**のが綺麗。ただし theme.css 肥大の懸念あり → karte.html.j2 ローカル style でも可。判断は次セッションで

### 注意点

- events 全件出すと長尺カルテ（例: Gemini = 多ヒット）でページが縦に伸びる
  - 目次 (TOC) を冒頭に置くか、`<details>` で折りたたみにするか要検討
  - ユーザー回答は「全件」なので、まずは全件展開で実装し、長すぎたら次々セッションで折りたたみ案
- フィードページの `feature` クラス（先頭強調）は使わない方が無難（カルテ内では均一表示が読みやすい）

### 完了条件

- 全 21 カルテ再生成後、events を持つ entity（例: claude-opus, gemini）で最下段にフィード表示
- 47 PASS 維持 + 新規テスト 1 件追加（`build_context` 結果に各 karte.feed_items が入っているか）
- E2E（任意）: desktop 1280 + mobile 390 で karte ページの縦スクロール確認

## 3. フィードトップの動的タイトル（`<h1 data-digest>`）に News-Grasp 風の下線マーカー強調

### 現状

- 該当 HTML: [templates/index.html.j2:210](../templates/index.html.j2#L210) 付近の `<h1 data-digest>今日、生成AIで何が起きたか。</h1>`
- 実出力例: 「DeepSeek slated to raise $7 billion in maiden funding round, sources say ― 本日はモデル/LLMが主役。」
  - 採用記事の英語タイトル + 「— 本日は{カテゴリ}が主役。」を合成（実装は `app.js` の `data-digest` 書き換えロジック）
- 該当 CSS: [templates/index.html.j2:22](../templates/index.html.j2#L22) `.feed-head h1 { font-size: clamp(32px, 4.8vw, 54px); ... }`
- 問題: タイトルが長くなり、行折り返しでメリハリが弱い

### ユーザー要件

- News-Grasp トップページの **下線マーカー風強調** を移植して可読性アップ
- 「タイトルも長くなってきた」≒ 主要キーワード（製品名・金額・組織）を一発で目立たせたい意図と推察

### 設計案メモ（次セッションで検証）

- **News-Grasp 側の実装確認が先**: `~/Obsidian/New's Grasp/News-Grasp` または `HIDEPON-UMG/News-Grasp` リポの index/トップページ HTML/CSS を Read
  - 推定キーワード: `marker`, `highlight`, `underline`, `<mark>`, `linear-gradient.*transparent`
- 典型パターン（News-Grasp 採用予想）:
  ```css
  .digest mark {
    background: linear-gradient(transparent 55%, color-mix(in oklab, var(--accent) 60%, transparent) 0);
    padding: 0 2px;
    color: var(--fg);
  }
  ```
  - これだと「行下半分にアクセント色の太い下線」が乗る News-Grasp 風
- AI-Pulse 側適用: `data-digest` の JS 出力に `<mark>` を入れる必要あり
  - 主要キーワード抽出は決定論で難しい → Gemini に「強調すべきキーワード 1〜3 語」を返させるか、`app.js` の digest 合成時に固定パターン（記事の `entity.name` を `<mark>` で包む）が現実的
  - **判断は次セッションで**: 「自動キーワード抽出」vs「entity 名のみマーカー」vs「カテゴリ名のみマーカー」
- 色指定は DESIGN.md トークン経由（`var(--accent)` の color-mix が無難）

### 完了条件

- index.html を desktop / mobile で目視確認、主要キーワードが「一目で」見える
- DESIGN.md lint errors=0 / 47 PASS 維持
- 不可視テキストや行高ズレが出ないこと（`background-clip` 系は注意）

### 補足

- 1 件目（将来シナリオラベル）と CSS グラデの実装パターンが似ている（`background: linear-gradient + background-clip: text`）。
  共通化できるか検討すると保守性が上がるが、まずは個別に実装してから抽出するのが安全。

## 守るべき制約（前セッション継続）

- 既存 47 PASS を**一切いじらない**
- DESIGN.md トークン経由で色・余白指定（直書き禁止）
- コミットは明示 GO 待ち / push は明示 GO 待ち
- スキーマ変更を伴わない（events.jsonl / entities.jsonl は無修正）

## 関連 memory

- `feedback_impact_analysis_before_modification`（karte.html.j2 改修前に呼出元を全列挙）
- `feedback_match_advice_against_memory`（「フィードと同じレイアウト」要件を index.html.j2 と照合）
- `reference_design_md_skill`（DESIGN.md lint 必須）
- `feedback_test_before_report`（47 PASS + 実測値報告）
