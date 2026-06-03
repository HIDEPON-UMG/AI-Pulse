# 引継ぎ: AI-Pulse パイプライン構築完了（2026-06-03 更新）

次セッションの主題は **「GitHub Pages 公開（private→public + GitHub Actions ワークフロー）」**。

---

## 1. 現在の状態（事実）

| 項目 | 値 |
| --- | --- |
| カルテ（L1） | **21件**（`data/entities.jsonl`） |
| イベント（L2） | **120件**（`data/events.jsonl`）—今日 25→120 に増加 |
| サムネイル補完 | **85/120件**（`thumb` フィールド付与済み）|
| パイプライン | **日次・週次バッチ運用中**（Task Scheduler 登録済み）|
| pytest | **38 PASS** |
| sw.js CACHE | `aipulse-v5` |
| Git | private repo `HIDEPON-UMG/AI-Pulse` の `origin/master`（未push分あり）|

### カルテ内訳（21件）

| レンズ | entity_id |
| --- | --- |
| model（5件） | claude-opus / qwen / deepseek / gemini / llama |
| editor（2件） | cursor / windsurf |
| physical（3件） | physical-intelligence / figure / tesla-optimus |
| media（2件） | flux / runway |
| agent（4件） | devin / agentkit / dify / langgraph |
| infra（3件） | vera-rubin / ironwood-tpu / cosmos |
| policy（2件） | eu-ai-act / japan-ai-act |

---

## 2. 今日構築したパイプライン（参照用）

```
毎日 7:00 → scripts/run_daily.bat
              └─ python tools/run_daily.py
                   Step1: collect_rss.py  （Google News RSS → L2 events）
                   Step2: NotebookLM fast 更新（当日更新エンティティのみ）
                   Step3: backfill_thumb.py（source_url → og:image → thumb）
                   Step4: generate_pages.py（site/ 再生成）

月曜 7:00  → scripts/run_weekly.bat
              └─ python tools/run_weekly.py
                   全21エンティティを NotebookLM deep 更新 → site/ 再生成
```

**Task Scheduler 登録名**: 「AI-Pulse 日次バッチ」「AI-Pulse 週次バッチ」

ログ出力先: `AI-Pulse/_logs/daily_YYYYMMDD.log` / `weekly_YYYYMMDD.log`

---

## 3. フィードレイアウト（今日変更済み）

デスクトップ（>860px）: `80px 180px 1fr`（スコア | サムネイル | 本文）
タブレット（601〜860px）: `64px 140px 1fr`
モバイル（≤600px）: `64px 1fr`（スコア+サムネイル1行目）→ 本文全幅2行目

サムネイルは `app.js` の `initThumbs()` が `data-thumb` → `img.src` にセット。
エラー時は `thumb-{cat}.svg` にフォールバック。

---

## 4. 残タスク一覧（received − done の差分）

| 優先 | タスク | 設計ポインタ |
| --- | --- | --- |
| 🔴 **P0** | **GitHub Pages 公開**（private→public + Actions ワークフロー） | 下記「5. GitHub Pages 公開手順」参照 |
| 🟡 P1 | 各カルテへの手動キュレーション記事補完 | RSS で 1〜5 件は入ったが品質高い手動記事で 3 件以上にしたい |
| 🟡 P1 | ロゴ意匠の目視評価 | パルス線＋ニューロン節点＋シナプス枝モチーフ。`site/icon.svg` を確認して要否判断 |
| 🟡 P1 | relations の出典 URL 付与 | `data/entities.jsonl` の `relations[].source_url` が一部空 |
| 🟢 P2 | `prompts/breaking_websearch.md` 廃止宣言 | claude -p 方式廃止→collect_rss.py 使用を明記 |
| 🟢 P2 | onclick source_url JS hardening | `data-href` + delegated handler 化。非 exploitable だが筋通し |
| ⏸️ | ClaudeCodeFeed 撤去 | 不可逆・明示的 GO 待ち |

---

## 5. GitHub Pages 公開手順（次セッションで実施）

### 必要な判断（事前確認ずみの選択肢）

1. **カスタムドメイン**: 使わない場合 → URL は `https://HIDEPON-UMG.github.io/AI-Pulse/`
2. **フォント**: Google Fonts CDN のまま（オンライン前提・今すぐ可）で判断済みなら OK

### 実装手順

1. `.github/workflows/deploy.yml` を作成:

```yaml
name: Deploy to GitHub Pages
on:
  push:
    branches: [master]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install jinja2
      - run: python tools/generate_pages.py
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site/
      - id: deployment
        uses: actions/deploy-pages@v4
```

2. `git commit` + `git push`
3. GitHub リポジトリを **public** に変更（Settings → Danger Zone）
4. GitHub → Settings → Pages → Source を **GitHub Actions** に設定

### data/ の扱い

`data/events.jsonl`（120件）と `data/entities.jsonl` は公開情報のみなので public 化しても問題なし。

### 日次バッチ後の自動 push（オプション）

`run_daily.bat` に以下を追記すれば、毎日 7:00 に自動 push → GitHub Pages が自動更新される:

```bat
cd /d "%AI_PULSE%"
git add data\events.jsonl data\entities.jsonl site\
git commit -m "daily update %DATE%" --allow-empty
git push origin master
```

**注意**: `git push` は不可逆操作なので、`safe-commit` スキルを通してから追記すること。

---

## 6. 関連ファイル一覧

| ファイル | 役割 |
| --- | --- |
| `tools/collect_rss.py` | RSS 収集・L2 events 生成 |
| `tools/backfill_thumb.py` | OGP サムネイル補完 |
| `tools/run_daily.py` | 日次バッチ本体 |
| `tools/run_weekly.py` | 週次バッチ本体（NotebookLM deep） |
| `tools/research_notebooklm.py` | `build_carte_fields`（axis ごと ask・claude -p 不要） |
| `tools/fetch_ogp.py` | OGP 取得（urllib + html.parser） |
| `scripts/run_daily.bat` | Task Scheduler エントリポイント（日次） |
| `scripts/run_weekly.bat` | Task Scheduler エントリポイント（週次） |
| `templates/index.html.j2` | フィードレイアウト（スコア→サムネイル→本文） |
| `static/sw.js` | PWA Service Worker（CACHE=aipulse-v5） |

---

## 7. 次セッションの始め方

```
AI-Pulse の続き。
docs/handoff_2026-06-03_pipeline_done.md を読んで現状（21カルテ・120イベント・
日次バッチ稼働中）を把握してから、GitHub Pages 公開（private→public + 
GitHub Actions ワークフロー .github/workflows/deploy.yml の作成）を進めて。
カスタムドメインは使わない（URL = https://HIDEPON-UMG.github.io/AI-Pulse/）。
フォントは Google Fonts CDN のまま。
```
