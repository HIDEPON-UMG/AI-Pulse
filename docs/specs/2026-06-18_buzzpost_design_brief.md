# BuzzPost Design Brief for Claude Design

## 背景

AI-Pulse に `BuzzPost` メニューを追加し、生成AIコミュニティで当日話題になっている X 投稿を日次バッチで収集して閲覧できるページを作っている。

現在の実装は未完成。直近の画面は RSS から取得した本文と URL を自前カードに表示しただけで、ユーザー要件である「X の投稿をそのまま見せる」状態を満たしていない。デザイン検討では、X 投稿を主役として扱う画面に作り直す必要がある。

## ユーザー要件

- BuzzPost は AI-Pulse のメニューに置く。
- 用途は、AI-Pulse の生成AIカテゴリ周辺について、コミュニティ動向やバズっている投稿を当日単位で確認すること。
- 日次バッチに含める。
- X の投稿は要約カードではなく、投稿そのものとして見せる。
- スコア 0 や弱い反応の投稿は載せない。
- スコアリングは絶対数と伸び率の複合。
- メニューバー文言は英語に統一する。

## 現在収集している情報

収集元は X RSS。既存の閲覧用 X サブアカウントと RSS 生成基盤を流用する想定。

既定の RSS 入力:

- `../twitter-rss/output`
- 環境変数 `BUZZPOST_X_RSS_PATHS` があればそれを優先

対象 RSS 名とカテゴリ:

| RSS 名 | カテゴリ | 表示ラベル | グリフ |
|---|---|---|---|
| `buzzpost-model` | `model` | モデル/LLM | ◆ |
| `buzzpost-editor` | `editor` | AIエディタ・コーディング | ▲ |
| `buzzpost-agent` | `agent` | エージェント・ツール | ■ |
| `buzzpost-media` | `media` | 画像・動画・音声生成 | ◎ |

公開 JSONL の主な行フィールド:

| フィールド | 内容 |
|---|---|
| `date` | 観測日 |
| `category` | `model` / `editor` / `agent` / `media` |
| `category_label` | 表示カテゴリ名 |
| `glyph` | カテゴリ記号 |
| `source` | `x-rss:buzzpost-model` のような収集元 |
| `source_query` | RSS channel description/title 由来の検索クエリ |
| `post_url` | X 投稿 URL |
| `title` | RSS title 由来。表示主役にしない |
| `text` | RSS description 由来の投稿本文。改行と URL を保持 |
| `published_at` | 投稿日時 |
| `buzz_score` | `absolute_score + velocity_score` の丸め値 |
| `absolute_score` | 反応絶対数スコア |
| `velocity_score` | 時間あたり伸び率スコア |
| `engagement` | likes / reposts / replies / quotes |

スコア計算:

```text
absolute_score = likes + reposts * 2 + replies * 2 + quotes * 2
velocity_score = absolute_score / max(age_hours, 1.0)
buzz_score = round(absolute_score + velocity_score)
```

掲載閾値:

```text
BUZZPOST_MIN_ABSOLUTE_SCORE = 25
BUZZPOST_MIN_VELOCITY_SCORE = 8.0
掲載条件 = absolute_score >= 25 OR velocity_score >= 8.0
```

現在の実データ状態:

```json
{
  "latest": "2026-06-18",
  "candidate_count": 73,
  "collected": 0,
  "written": 0,
  "dropped_threshold": 73,
  "dropped_duplicate": 0,
  "degraded": 0,
  "min_absolute_score": 25,
  "min_velocity_score": 8.0
}
```

つまり RSS 収集自体は候補 73 件を見つけているが、現在の閾値では掲載対象が 0 件。

## ページの基本構成

現在の `buzz-posts.html` は以下の構成。

1. 共通ヘッダー
   - `Feed`
   - `Archive`
   - `Karte`
   - `Repositories`
   - `BuzzPost`

2. BuzzPost ヘッダー
   - 日付
   - `BuzzPost / COMMUNITY SIGNAL`
   - 投稿件数
   - 見出し: `生成AIコミュニティのバズ投稿`
   - 説明文
   - latest / source / read-only observation layer

3. ツールバー
   - 検索 input
   - `All`
   - カテゴリフィルタ

4. 一覧ヘッダー
   - `本日の観測ポスト`
   - 表示件数

5. 投稿カード
   - buzz score
   - カテゴリバッジ
   - 投稿表示領域
   - source / query タグ
   - date / published_at
   - X 投稿を開くリンク

6. 空状態
   - 収集未実行なのか、閾値落ちなのかを表示
   - 候補数、掲載数、閾値未満数、RSS 状態
   - 掲載閾値

## デザイン上の必須修正

現在の投稿カードは完成形ではない。Claude Design へ依頼したい主眼は次。

### 必須

- X 投稿を主役にする。
- 可能なら公式 X 埋め込みの見た目に寄せる。
- HTML 実装では `blockquote.twitter-tweet` と `https://platform.twitter.com/widgets.js` を使う想定。
- X 側の widget が描画できない場合だけ fallback として本文・URLを表示する。
- 生成タイトル `title` は主表示しない。
- `text` は fallback 用。主表示は `post_url` を元にした X 埋め込み。
- Buzz score やカテゴリは補助情報として置く。投稿本体より強くしない。

### 避ける

- 自前カードに本文と URL を置いただけの表示。
- 投稿本文が「ニュース要約」や「AI-Pulse 記事カード」に見える表示。
- Buzz score が投稿本体より目立ちすぎる構成。
- source_query のタグが投稿本文より視線を奪う構成。

## Claude Design への依頼文

```text
AI-Pulse の BuzzPost ページを再設計してください。

目的:
生成AIコミュニティで当日バズっている X 投稿を、ニュース化前の関心シグナルとして確認するページです。ユーザーは「Xの投稿そのもの」を見たいので、自前の要約カードではなく、X投稿が主役に見える UI にしてください。

現在のデータ:
- post_url: X投稿URL
- text: RSSから取得した投稿本文。fallback用
- category/category_label/glyph: model/editor/agent/media の分類
- buzz_score/absolute_score/velocity_score/engagement: 反応スコア
- source/source_query: 収集元とRSS検索条件
- published_at/date: 投稿日時と観測日

必須要件:
- 投稿本体は X の公式埋め込みに近い見た目、または `blockquote.twitter-tweet` を置く前提のレイアウトにする
- `title` は主表示しない
- fallback として本文とURLを表示する場所は用意する
- buzz score は補助情報として表示し、投稿本体より目立たせない
- カテゴリフィルタと検索は維持
- 0件時は「収集失敗」ではなく「候補はあるが閾値未満」も判断できる
- AI-Pulse 既存の dark / editorial / serif 見出しトーンに合わせる

避けたいもの:
- 本文とURLをただ四角い箱に流し込んだだけのカード
- X投稿ではなくニュースカードに見える構成
- スコアやタグが投稿本体より強い構成

想定ページ構成:
1. Header nav: Feed / Archive / Karte / Repositories / BuzzPost
2. Hero: 日付、BuzzPost / COMMUNITY SIGNAL、投稿件数、説明文
3. Sticky toolbar: search + category chips
4. Feed list: X post embed as primary content
5. Metadata rail: score, category, observed date, source query
6. Empty state: candidate_count, collected, dropped_threshold, thresholds, RSS status

成果物:
- Desktop 1440px と mobile 390px のレイアウト案
- 投稿カード 1件表示の具体案
- 空状態の具体案
- 実装で使う CSS class 構成案
```

## 現在の未完了状態

直前に `tests/test_generate.py::TestGenerate::test_buzzpost_page_is_built_from_public_rows` へ、X埋め込みを要求する Red テストを追加済み。

現在の期待:

- `class="x-embed-shell"` がある
- `<blockquote class="twitter-tweet"` がある
- `data-theme="dark"` がある
- `https://platform.twitter.com/widgets.js` がある
- `Generated title must not be shown` がない

現在の状態:

- この Red テストは未実装のため失敗する。
- `templates/buzz-posts.html.j2` はまだ `div.x-post-text` に本文と URL を表示するだけ。
- `site_preview/` は確認用生成物で未追跡。
