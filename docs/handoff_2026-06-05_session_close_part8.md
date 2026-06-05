# Handoff 2026-06-05 session close — Part 8 (WAI Series カルテ追加)

Part 7 (rationale schema 強化 + 24 件遡及再生成) 完了後、media カテゴリに WAI シリーズの新規カルテを追加した小規模差分セッションのクローズ。コード/スキーマ/テストの変更はなく、`data/entities.jsonl` への 1 entity 追加のみ。

## 今回やったこと

### 1. WAI Series カルテを media カテゴリに追加 (1 entity)

`entity_id=wai-series` を `data/entities.jsonl` に append。当初は `wai-anima` 単独 entity として 1 件足したが、ユーザー指摘 (「WAI は Anima 以外にもいろいろ作ってきたのでシリーズとして 1 件にまとめてはどうか」) を受けて `wai-series` 1 件に再構成した。

- **vendor**: WAI0731 (Civitai community creator)
- **positioning**: Illustrious 源流 (WAI-illustrious-SDXL / 累計 77K+ DL) を起点に、REALISM・Anima ベース派生を短サイクルで量産。約 20 ヶ月で v17.0 までほぼ月 1 ペース更新を継続
- **history (3 件 / 新しい順)**:
  | when | title | URL | 取得元 |
  |---|---|---|---|
  | 2026.06 | WAI-ANIMA v1.0 (Anima ベース派生) | civitai.com/models/2544636/wai-anima | Civitai (WebFetch 200) |
  | 2025.12 | WAI-REALISM-Illustrious v1.0 | civitai.com/models/2233797/wai-realism-illustrious | Civitai (WebFetch 200) |
  | 2024.10 | WAI-illustrious-SDXL 源流 (v17.0 / 77,064 DL) | civarchive.com/models/827184 | CivArchive (WebFetch 200) |
- **comparison**: WAI Series 総称 / Anima Base (親) / FLUX の 3 列

### 2. WAI-illustrious-SDXL 源流の 2 次情報採用

Civitai 本サイト (mature 認証経由で civitai.red リダイレクト) では詳細取得不可だったため、当初は history に URL 無しの暫定エントリを置いていた。CivArchive (`civarchive.com/models/827184`) と Anifusion (`anifusion.ai/models/wai-illustrious/`) の 2 次情報源クロスチェックで以下を確認、正式エントリに書き換えた:

- 初版 2024-10-05 (Anifusion)
- 最新 v17.0 公開 2026-06-05 (CivArchive・今日)
- ベース Illustrious XL
- 累計 77,064 ダウンロード (CivArchive)
- 推奨 Euler A / Steps 28 / Guidance 7

**ユーザー方針確認: CivArchive は画像・動画生成カルテにおいて信頼できる 2 次情報源として採用 OK。**

### 3. 除外判断

- WAI-illustrious-Mix-FP8 (civitai 2451718): 別作者 (MorikoMorizz) の量子化派生。シリーズ本流から除外
- WAI-NSFW-Illustrious-SDXL 等: WebFetch 200 未確認のため history に含めず (将来確認時点で追記する設計)

## 実測値

| 項目 | 値 |
|---|---|
| pytest | 93 PASS / 1 skipped (URL E2E live) / 0 FAIL |
| validate_store | entities 29→30 / events 171 (参照整合 OK) |
| audit_urls --gate | 191→194 / 194 OK / exit=0 (新規 3 URL 全件 200) |
| URL 偽造 | 0 件 (WebFetch クロスチェック済み URL のみ entity に記載) |
| 個人情報スキャン | clean (email/phone/api_key/aws_key 0 件) |
| URL 危険文字スキャン | clean (`_URL_FORBIDDEN_CHARS` 違反 0 件) |
| Gemini API 課金 | $0 (LLM 未起動・WebSearch + WebFetch のみ) |
| media カテゴリ件数 | 4 → 5 (flux / runway / qwen-image / anima-base / **wai-series**) |
| working tree (commit 前) | `M data/entities.jsonl` のみ |

## 残タスク (Part 5/6/7/8 統合)

優先順は Part 7 handoff から継承。今回追加分 (★) は wai-series 関連の小規模フォロー。

### P0 (Part 5 から継続・最高優先)

- **2026-06-06 朝 7:00 Task Scheduler 起動の観察**
  - `AI-Pulse/_logs/daily_20260606.log` が UTF-8 文字化けなしで生成されるか
  - 新規採用 entry に headline_ja が自動付与されるか
  - 新規採用 entry の rationale 3 軸が 20+ 字を満たすか (= Part 7 schema 強化が collect_rss でも有効か実機確認)
  - 満たさない場合 `llm_local._call_once` の schema retry で救えるか実測。救えなければ collect_rss が当該記事をドロップする = 採用率低下

### P1 (Part 6/7 残)

1. **LLM 意味反転誤訳の全件監査** (Part 6 残 #2)
   - 既存 entry に Part 7 schema 通過前の意味反転誤訳が残っていないか全件レビュー
   - 着手条件: ユーザーから「他にも誤訳がないか確認したい」と指示があった時のみ
2. **rationale の字数上限 (maxLength) 追加検討** (Part 7 残 #2)
   - 現状は minLength=20 のみ。上限を `maxLength=100` 等で縛るか
   - 着手条件: ユーザーから「字数上限も付けたい」と指示があった時のみ
3. **collect_rss 側の entity_context 渡し方統一** (Part 6 残 + Part 7 残 #4)
   - `collect_rss._make_event` は `translate_headline_ja` に entity_context を渡す
   - 一方 `apply_headline_ja` / `regenerate_rationale` は entity_context=None 固定
   - 揃え方の方針確認 (collect_rss を None に統一 / 遡及スクリプトに渡す方向で統一) が必要
   - 着手条件: ユーザー指示があった時のみ

### P2 ★ Part 8 新規 (wai-series 関連)

1. **CivArchive 採用方針の memory 保存**
   - `reference_civarchive_secondary_source.md` を新規作成
   - rule: AI-Pulse の画像・動画生成カルテで Civitai 本サイトが mature 認証等で取れない時、CivArchive (`civarchive.com/models/<id>`) を 2 次情報源として URL に採用してよい
   - scope: 画像・動画生成のみ (それ以外は適用外)
   - 由来: 2026-06-05 wai-series の WAI-illustrious-SDXL 源流エントリでユーザー方針確認
   - 着手条件: ユーザーから保存指示があった時に書く (内容案は既に握っている)
2. **WAI シリーズ追加派生の追跡** (発生時のみ)
   - WAI-NSFW-Illustrious-SDXL 等の他派生で WebFetch 200 確認できた時点で `wai-series.history` に追記
   - WAI-illustrious-SDXL の v18 以降が公開された時、`note` 内の「v17.0 / 約 20 ヶ月で 17 バージョン」の数値を更新
3. **anima-base と wai-series の双方向リンク** (任意)
   - 現状: wai-series.history で「Anima Base v1.0 を起点」と参照、wai-series.competitors に `anima-base` を含む
   - 逆方向: `anima-base.competitors` または将来 `related_entities` で `wai-series` を参照する案
   - 着手条件: 双方向リンク必要と判断された時のみ (現状の外科的変更原則では未着手)

### P3 (継続オープン項目)

- AI-Pulse のメイン主題「**記事増加**」(events 3 件 / entities 30 件 / physical データ 0 件 / パイプライン未ライブ運用) は Part 4 引継ぎ `docs/handoff_2026-06-03_articles_expansion.md` に集約済み

## コミット内容 (本 Part 8)

- `data/entities.jsonl`: wai-series entity を 1 行 append (+1 行)
- `docs/handoff_2026-06-05_session_close_part8.md`: 本ファイル (新規)

push 先: `HIDEPON-UMG/AI-Pulse` origin/master
