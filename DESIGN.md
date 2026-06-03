---
version: alpha
name: AI-Pulse
description: Dark base × Cool-tech (blue→cyan) のエディトリアル・ニュース UI。NewsPicks 風の中性 near-black に明朝（Noto Serif JP）を重ね、6 レンズ各色＋グリフで一覧を瞬時分類する。姉妹サイト News-Grasp の gold / Claude.ai の orange とは温度感・主色で明確に区別する。
colors:
  # ---- Neutrals (Palette A default / near-black 漆黒) ----
  bg: "#101113"
  bg-elev: "#191B1D"
  bg-elev-2: "#242629"
  fg: "#EEEFF1"
  fg-sub: "#AAACB1"
  fg-mute: "#727479"
  border: "#2C2E31"
  border-soft: "#212225"
  border-strong: "#45484C"
  # ---- Primary accent: Palette A "Cyan Signal" ----
  accent: "#36DCEC"
  accent-2: "#00B7E3"
  accent-fg: "#02121A"
  # ---- Category accents (6 lenses / text-on-dark) ----
  c-model: "#70ADFE"
  c-editor: "#48D8DF"
  c-media: "#E291EE"
  c-agent: "#66DC9E"
  c-infra: "#F5C25F"
  c-policy: "#FF8977"
  # ---- Category solids (badge fills / white text・AA 検証済) ----
  c-model-solid: "#3262BF"
  c-editor-solid: "#007290"
  c-media-solid: "#9738A6"
  c-agent-solid: "#007747"
  c-infra-solid: "#8F5A04"
  c-policy-solid: "#BC3425"
  # ---- Importance heat ----
  imp-high: "#FF7264"
  imp-mid: "#F5C25F"
  imp-low: "#81878D"
  # ---- Relationship semantics (karte) ----
  rel-capital: "#66DC9E"
  rel-tech: "#70ADFE"
  rel-rival: "#FF7264"
  rel-std: "#C39DFF"
  # ---- Source tiers ----
  tier-1: "#66DC9E"
  tier-2: "#48D8DF"
  tier-3: "#81878D"
typography:
  display:
    fontFamily: "'Noto Serif JP', 'Hiragino Mincho ProN', 'Yu Mincho', serif"
    fontSize: 54px
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.02em"
  h1:
    fontFamily: "'Noto Serif JP', 'Hiragino Mincho ProN', 'Yu Mincho', serif"
    fontSize: 34px
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.02em"
  h2:
    fontFamily: "'Noto Serif JP', 'Hiragino Mincho ProN', 'Yu Mincho', serif"
    fontSize: 20px
    fontWeight: 700
    lineHeight: 1.4
    letterSpacing: "-0.01em"
  h3:
    fontFamily: "'Noto Serif JP', 'Hiragino Mincho ProN', 'Yu Mincho', serif"
    fontSize: 17px
    fontWeight: 600
    lineHeight: 1.3
  body-md:
    fontFamily: "'Noto Serif JP', Georgia, 'Times New Roman', serif"
    fontSize: 16px
    lineHeight: 1.7
  body-sm:
    fontFamily: "'Noto Serif JP', Georgia, 'Times New Roman', serif"
    fontSize: 14px
    lineHeight: 1.75
  label:
    fontFamily: "'JetBrains Mono', ui-monospace, 'SFMono-Regular', Menlo, monospace"
    fontSize: 12px
    fontWeight: 400
    letterSpacing: "0.08em"
  mono:
    fontFamily: "'JetBrains Mono', ui-monospace, 'SFMono-Regular', Menlo, monospace"
    fontSize: 12.5px
    letterSpacing: "-0.01em"
rounded:
  none: 0px
  sm: 2px
  md: 4px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  2xl: 48px
  3xl: 64px
components:
  story-card:
    backgroundColor: "{colors.bg-elev}"
    textColor: "{colors.fg}"
    rounded: "{rounded.sm}"
    padding: 24px
    typography: "{typography.body-md}"
  cat-badge:
    backgroundColor: "{colors.c-model-solid}"
    textColor: "#FFFFFF"
    rounded: "{rounded.sm}"
    padding: 8px
    typography: "{typography.h2}"
  chip:
    backgroundColor: "{colors.bg-elev}"
    textColor: "{colors.c-editor}"
    rounded: "{rounded.sm}"
    padding: 8px
    typography: "{typography.body-sm}"
  chip-active:
    backgroundColor: "{colors.c-editor-solid}"
    textColor: "#FFFFFF"
    rounded: "{rounded.sm}"
    padding: 8px
    typography: "{typography.body-sm}"
  chip-all:
    backgroundColor: "{colors.bg-elev}"
    textColor: "{colors.fg-sub}"
    rounded: "{rounded.full}"
    padding: 8px
    typography: "{typography.body-sm}"
  search-input:
    backgroundColor: "{colors.bg-elev}"
    textColor: "{colors.fg}"
    rounded: "{rounded.sm}"
    padding: 12px
    typography: "{typography.body-sm}"
  karte-link:
    backgroundColor: "{colors.bg-elev}"
    textColor: "{colors.accent}"
    rounded: "{rounded.sm}"
    padding: 8px
    typography: "{typography.mono}"
  count-pill:
    backgroundColor: "{colors.bg-elev}"
    textColor: "{colors.fg-mute}"
    rounded: "{rounded.sm}"
    padding: 8px
    typography: "{typography.label}"
---

## Overview

**AI-Pulse** は生成AIニュースの分析サイト兼DB。新着フィードを入口に、各ニュースから対象サービス/モデルの「分析カルテ」へ深掘りする 2 層構造を持つ。デザインの性格は **Dark base × Cool-tech（青→シアン）のエディトリアル**。NewsPicks のダークモードを参照した中性的な漆黒（near-black、純黒は使わない）にオフホワイトのテキストを重ね、見出しから本文・タグまで **明朝（Noto Serif JP）** で組むことで「端末的な先進性」と「新聞的な信頼感」を両立させる。

主な性格:

- **中性 near-black 基調**: 背景は純黒ではなく `#101113`。白い内側区切り線を避け、`border` トークンの低コントラスト罫線でカードの塊感を保つ（NewsPicks 設計指針）。
- **明朝エディトリアル**: 見出し・記事タイトル・タグ・チップまで Noto Serif JP（明朝）。数値・コード・ラベルのみ JetBrains Mono の等幅。UI 一部の補助に Noto Sans JP。
- **6 レンズ＝色＋グリフ**: 6 カテゴリそれぞれに固有アクセント色とグリフ（◆▲◎■▶✦）を割り当て、読者は色とマークだけで一覧を瞬時に分類できる。
- **硬質な角**: 角丸は 0〜4px に抑える。フル丸（pill）は「All」フィルタボタンなど限定用途のみ。
- **切替パレット**: 主色は 3 案（Cyan Signal / Azure Deep / Ion）を `[data-palette]` で切替・永続化。既定は Cyan Signal。

> **News-Grasp / Claude.ai との区別（確定方針#7）**: 姉妹サイト News-Grasp は navy + cream + **gold** の角丸 0・ライト寄り。Claude.ai 公式トンマナは warm cream + **Claude Orange**。AI-Pulse は **ダーク基調 × シアン主色**で温度感・主色ともに明確に別物。gold / orange / cream は使わない。

> **トークンの正準ソース**: 実行時の正確な値（oklch・`clamp()` の流体サイズ・3 パレット定義）は [static/theme.css](static/theme.css) が一次ソース。本 DESIGN.md frontmatter は lint 互換のため **hex / 固定 px** に正規化した代表値を載せる（hex は theme.css の oklch から決定論変換）。実装は色・余白・角丸を直書きせず必ず CSS 変数（`var(--bg)` 等）を参照する。

> **意図的に component から参照していないトークン**: カテゴリ accent（text-on-dark 用）・importance・relationship・tier・各 solid・neutrals の一部は、実装側で罫線色・テキスト色・図解ノード塗り・スコア数値色に **直接参照**する前提。lint で `orphaned-tokens` warning が出るが意図通り。

## Colors

すべて oklch（共有 L/C・hue 変化）で設計。frontmatter は hex 正規化値、以下表は **theme.css の正確な oklch** を併記する。

### ニュートラル（Palette A "Cyan Signal" 既定）

| Token | oklch（正準） | hex | 用途 |
|:--|:--|:--|:--|
| `bg` | `0.178 0.004 265` | `#101113` | ページ背景。中性 near-black（純黒不可） |
| `bg-elev` | `0.220 0.005 265` | `#191B1D` | カード・ヘッダ・入力など一段持ち上げる面 |
| `bg-elev-2` | `0.268 0.006 265` | `#242629` | さらに持ち上げる面・サムネ地 |
| `fg` | `0.952 0.003 265` | `#EEEFF1` | 主要テキスト（オフホワイト・純白不可） |
| `fg-sub` | `0.745 0.007 265` | `#AAACB1` | 要約・補助テキスト |
| `fg-mute` | `0.560 0.008 265` | `#727479` | キャプション・metadata・非選択 |
| `border` | `0.300 0.006 265` | `#2C2E31` | 罫線・区切り |
| `border-soft` | `0.252 0.006 265` | `#212225` | 弱い区切り |
| `border-strong` | `0.400 0.008 265` | `#45484C` | スコアバー地・強い枠 |

### 主色アクセント（3 パレット切替）

| Palette | accent | accent-2 | accent-fg | 性格 |
|:--|:--|:--|:--|:--|
| **A Cyan Signal**（既定） | `0.82 0.130 205` → `#36DCEC` | `0.72 0.140 222` → `#00B7E3` | `0.17 0.030 230` → `#02121A` | 明るいシアン。最も視認性が高い |
| B Azure Deep | `0.70 0.155 254` → `#53A1FC` | `0.62 0.165 262` → `#4C82E8` | `#F4F8FF` | 青みの深いトーン（bg `#060B16`） |
| C Ion | `0.86 0.145 188` → `#25EFE3` | `0.78 0.150 196` → `#00D4D7` | `#040A0A` | 漆黒地のエレクトリック・シアン（bg `#040A0A`） |

### カテゴリアクセント（6 レンズ・共有 L/C・hue 変化）

text-on-dark 用の明色（`--cat`）と、バッジ塗り用の暗色 solid（`--cat-solid`・白文字で AA 通過）の 2 系統を持つ。

| レンズ | グリフ | accent oklch → hex | solid oklch → hex（白文字 AA） |
|:--|:-:|:--|:--|
| ① モデル/LLM | ◆ | `0.74 0.135 256` → `#70ADFE` | `0.515 0.155 262` → `#3262BF`（5.8:1） |
| ② AIエディタ・コーディング | ▲ | `0.81 0.120 200` → `#48D8DF` | `0.505 0.110 220` → `#007290`（5.1:1） |
| ③ 画像・動画・音声生成 | ◎ | `0.77 0.155 322` → `#E291EE` | `0.520 0.185 322` → `#9738A6`（6.0:1） |
| ④ エージェント・ツール | ■ | `0.81 0.140 158` → `#66DC9E` | `0.495 0.130 160` → `#007747`（5.2:1） |
| ⑤ インフラ・チップ | ▶ | `0.84 0.130 82` → `#F5C25F` | `0.515 0.110 70` → `#8F5A04`（5.8:1） |
| ⑥ 規制・資金・業界 | ✦ | `0.76 0.150 30` → `#FF8977` | `0.530 0.175 30` → `#BC3425`（5.6:1） |

### セマンティクス（重要度・企業間関係・出典ティア）

| Token | oklch → hex | 用途 |
|:--|:--|:--|
| `imp-high` | `0.72 0.175 28` → `#FF7264` | 重要度・影響度・話題性の「高」バー |
| `imp-mid` | `0.84 0.130 82` → `#F5C25F` | 同「中」 |
| `imp-low` | `0.62 0.012 252` → `#81878D` | 同「低」 |
| `rel-capital` | `#66DC9E` | カルテ企業間関係: 資本 |
| `rel-tech` | `#70ADFE` | 同: 技術依存 |
| `rel-rival` | `#FF7264` | 同: 競合 |
| `rel-std` | `0.77 0.150 300` → `#C39DFF` | 同: 標準化協調 |
| `tier-1` | `#66DC9E` | 出典 T1 公式 |
| `tier-2` | `#48D8DF` | 出典 T2 一次報道 |
| `tier-3` | `#81878D` | 出典 T3 二次 |

## Typography

3 ファミリ構成。可読性最優先で **本文まで明朝**に寄せる（最終決定はユーザー嗜好通り）。

- **見出し・本文・タグ（明朝）**: `Noto Serif JP` → `Hiragino Mincho ProN` / `Yu Mincho` / `serif`。記事タイトル・カテゴリバッジ・チップ・タグまでこのファミリ。
- **数値・ラベル・コード（等幅）**: `JetBrains Mono` → `ui-monospace` / `SFMono-Regular` / `Menlo`。スコア・日付・出典・`label` クラスに使い、`tabular-nums` で桁を揃える。
- **UI 補助（サンセリフ）**: `Noto Sans JP` → `system-ui`。ごく一部の小コントロールのみ。

流体見出しサイズ（theme.css の正準値・本表は frontmatter 固定値の由来）:

| ロール | 正準（clamp） | frontmatter 固定 | weight |
|:--|:--|:--|:--|
| display（動的見出し） | `clamp(32px, 4.8vw, 54px)` | 54px | 700 |
| h1 | `clamp(24px, 3.2vw, 34px)` | 34px | 700 |
| h2（記事タイトル） | 20px | 20px | 700 |
| h3 | 17px | 17px | 600 |
| body | 16px / line-height 1.7 | 16px | 400 |
| sm | 14px | 14px | 400 |
| label | 12px / letter-spacing 0.08em / uppercase | 12px | 400 |
| mono | 12.5px | 12.5px | 400 |

- 本文 `line-height` は **1.7**、`font-feature-settings: "palt" 1` で日本語の字詰めを最適化（長文可読性を最優先）。
- 見出しは `letter-spacing` 負値で詰める。weight は 700/900 を要所に。

## Layout

4 の倍数（4/8/16/24/32/48/64）を基準にした余白スケール。

| Token | px | 主用途 |
|:--|:--|:--|
| `xs` | 4 | アイコン・グリフ間 |
| `sm` | 8 | インライン要素間・チップ間 |
| `md` | 16 | フォーム要素間・メタ行 |
| `lg` | 24 | カード内パディング・wrap 左右 |
| `xl` | 32 | セクション見出し前後 |
| `2xl` | 48 | （予備） |
| `3xl` | 64 | フッタ前マージン |

- 最大コンテンツ幅 `--maxw`: **1180px**。固定ヘッダ高 `--header-h`: **84px**。
- ヘッダは `position: fixed` ＋ `backdrop-filter: blur` の半透明。カテゴリ chip バーは `position: sticky`（ヘッダ直下）。
- **ブレークポイント**: フィードの記事グリッド（`92px 1fr 184px`）は `max-width: 720px` で 1 カラムに落とし、サムネを先頭（`order:-1`）へ。

## Elevation & Depth

ダーク基調のため、影は「黒の重ね」で最小限に。明色サーフェスでなく `bg-elev` の段差で持ち上げを表現する。

| レベル | 値 | 用途 |
|:--|:--|:--|
| `shadow-1` | `0 1px 0 oklch(0 0 0 / 0.45)` | 罫線的な極薄段差 |
| `shadow-2` | `0 2px 10px oklch(0 0 0 / 0.40), 0 1px 0 oklch(0 0 0 / 0.50)` | カード・スティッキー |
| `shadow-pop` | `0 14px 40px oklch(0 0 0 / 0.55)` | ポップオーバー・モーダル |

- 主アクセントの強調には `--glow`（accent 32% 混色）を `::selection` やフォーカスに使う。
- 白い内側区切り線・強い白影は使わない（near-black の塊感を壊すため）。

## Shapes

硬質・エディトリアル。シャープ寄りの角で新聞・端末的トーンをつくる。

| Token | 値 | 用途 |
|:--|:--|:--|
| `rounded.none` | 0px | スコアバー・サムネ角・図解ノード |
| `rounded.sm` | 2px | カード・チップ・バッジ・入力・タグ（既定） |
| `rounded.md` | 4px | やや大きめのコンテナ |
| `rounded.full` | 9999px | **「All」フィルタボタン限定**（中立リセット用の pill） |

角丸は最大でも 4px。pill は機能的に「カテゴリ選択をリセットする中立ボタン」を他と差別化する目的でのみ使う。

## Components

### `story-card`

フィード 1 記事。`bg-elev` 面 ＋ `fg` テキスト、左に総合スコア（カテゴリ色の特大等幅数値）、中央に明朝の見出し＋2 行要約＋出典ティア、右にサムネ＋カルテ導線の 3 カラムグリッド。hover で `bg-elev` 化＋左ボーダーをカテゴリ色に点灯、見出しを accent 色へ。

### `cat-badge`

カテゴリバッジ。**カテゴリ solid 色のベタ塗り＋白文字**（記事ラベルとフィルタ選択 chip で同一スタイル）。グリフ（◆▲◎■▶✦）を先頭に付ける。6 solid はいずれも白文字で WCAG AA（≥5.1:1）通過済。frontmatter 代表値はモデル solid。

### `chip` / `chip-active`

カテゴリフィルタ。既定は全選択で各 chip がカテゴリ accent 色で点灯。`chip`（非選択時）は `fg-mute` でグレーアウト＋低 opacity。`chip-active`（選択中）は cat-badge と同じ **solid ベタ塗り＋白文字**。挙動: 既定全選択 → 押すと解除 → 「All」で全戻し。

### `chip-all`

「All」リセットボタン。カテゴリ色を持たない中立の `bg-elev` ＋ `fg-sub`、唯一 `rounded.full`（pill）。カテゴリ chip 群とは形で差別化する。

### `search-input`

キーワード検索。`bg-elev` ＋ `border`、focus で `accent` の輪郭。見出し・要約・出典を横断フィルタし、カテゴリ chip と併用可能。

### `karte-link`

「カルテを見る →」導線。`accent` テキスト＋ accent 45% 混色の細枠、hover で `accent-weak` 背景。矢印は hover で右へ 2px スライド。

### `count-pill`

表示件数（`08 / 08 件`）。等幅 `label` 書体、`accent` 色の強調数値。フィルタに連動してライブ更新。

## Do's and Don'ts

### ✅ Do

- 背景は **`bg` (#101113) の中性 near-black**。サーフェスの段差は `bg-elev` / `bg-elev-2` でつくる
- テキストは **オフホワイト `fg` (#EEEFF1)** とサブの `fg-sub` / `fg-mute` の階調で。純白は使わない
- カテゴリは **必ず色＋グリフのペア**で示す（色覚多様性への配慮・一覧の即時分類）
- 数値・日付・スコア・出典は **等幅（JetBrains Mono）＋ `tabular-nums`** で桁を揃える
- バッジ・選択 chip は **solid ベタ塗り＋白文字**で統一（記事ラベルとフィルタを同スタイルに）
- 余白は **4 の倍数**で揃える。角丸は 0〜4px に抑える
- 主色を変えたいときは `[data-palette]` の 3 案から選ぶ（個別に色を足さない）

### ❌ Don't

- **gold / Claude Orange / warm cream を使わない**（News-Grasp・Claude.ai との混同を避ける／確定方針#7）
- 純黒 `#000000` 背景・純白 `#FFFFFF` テキストを使わない（near-black ＋ オフホワイト）
- カテゴリ accent（明色）を**バッジのベタ塗り地**に使わない（白文字が AA を割る。塗りは必ず solid を使う）
- 白い内側区切り線・強い白影でカードの塊感を壊さない
- 角を大きく丸めない（pill は「All」ボタン限定。記事・バッジは 2px）
- 明朝の本文を sans に置き換えない（エディトリアルな信頼感が崩れる）。等幅は数値・コードのみに限定
