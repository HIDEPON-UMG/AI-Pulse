# 引継ぎ: AI-Pulse 収集パイプライン再設計の実装着手（2026-06-03 作成）

次セッションの主題は **「Gemini API Free Tier + trafilatura ベースの新収集パイプラインを実装し、1 回手動実行で 95 件 → 新方式の events に置き換えるところまで」**。Task Scheduler の切替は更に別セッション（不可逆寄り・別途 GO 待ち）。

---

## 1. なぜこの実装をやるか（前提）

現状の `tools/collect_rss.py` は Google News RSS から 95 件/日を取り込むが、`summary_points` と `rationale` が空のままで UI 上の情報密度が手製 25 件に大差している。前セッションで応急処置（HTML エンティティ unescape・出典名 suffix 除去・`_auto_rationale`・`source_url = item["link"]`）を入れたが、本質は LLM 要約の欠落。

`claude -p` / `claude --print` は将来 Anthropic 課金扱いになる前提のため除外（News-Grasp の同経路も参考にしない）。**Gemini API Free Tier**（15 RPM / 1500 RPD・課金カード不要）を採用して品質を取り戻す。

---

## 2. 確定方針 8 件（前セッションでユーザー承認済み）

| # | 論点 | 確定値 |
| --- | --- | --- |
| 1 | 一次取得 | Google News RSS 継続（`tools/collect_rss.py` 流用） |
| 2 | 本文取得 | trafilatura ライブラリ（Apache2.0） |
| 3 | LLM 経路 | Gemini API Free Tier（`google-genai` SDK + `response_schema` JSON mode） |
| 4 | 既存 RSS 95 件 | 全削除して新方式で再生成（手製 25 件は `-rssNN` 命名ではないので無傷） |
| 5 | `event_id` 命名 | `-gemNN` 接尾辞（例: `2026-06-03-claude-opus-gem01`） |
| 6 | `summary` 言語 | 日本語で統一（手製 25 件の英文 → 日本語化は本実装スコープ外） |
| 7 | score / importance / event_type | Gemini に任せる。Python は `config.SCORE_MIN` 閾値フィルタだけ残す |
| 8 | スコープ | 実装 + 手動検証（1 回手動実行 + 契約テスト + E2E）まで。Task Scheduler は別セッション |

---

## 3. 設計ドキュメント（次セッション冒頭で必ず読む）

1. **最終プラン (Markdown)**: `C:\Users\hidek\.claude\plans\ai-pulse-wise-tide.md`
   - Section 1〜10 を順に読む。Section 3 (新規/改造ファイル一覧)・Section 4 (per entity loop)・Section 5 (Gemini 接続)・Section 7 (契約テスト案) が実装の主要参照
2. **HTML 仕様書 (5 タブ構成)**: `AI-Pulse/docs/specs/2026-06-03_collection-pipeline-redesign.html`
   - VSCode Live Preview または `start file:///...` で開く
   - 「パラメータ」タブの playground で GEMINI_RPM / ARTICLE_FETCH_TIMEOUT / MAX_BODY_CHARS / MIN_BODY_CHARS / SCORE_MIN を触り、「プロンプトとしてコピー」で `tools/config.py` の値が確定する
3. **本引継ぎ書 (Markdown)**: 本ファイル

---

## 4. 次セッション着手前にユーザーがやること

- [ ] [Google AI Studio](https://aistudio.google.com/apikey) で Gemini API キーを生成
   - **課金カード登録不要**で Free Tier 利用可能（95 件/日は RPD の 6.3%・余裕）
   - Google アカウントでサインインしてキーをコピー
   - 次セッション冒頭で Claude に渡す（または事前に `AI-Pulse/.env` に `GEMINI_API_KEY=...` を書いておく・`.env` は次セッションで `.gitignore` に追加される）

---

## 5. 次セッションでの実装順序（推奨）

### Step 0: 実装前確認（最初の 10 分）

| 項目 | 確認方法 |
| --- | --- |
| trafilatura が Google News redirect URL を解決できるか | `scripts/probe_gnews_redirect.py` を 5-10 行で書き、3 件の実 URL を `urllib.request.urlopen` + `Location` ヘッダで追跡。302 解決可なら素直に進める。200+JS なら `<source url>` 属性 + 中間 HTML の canonical link 探索を `fetch_article.resolve()` に追加 |
| `tools/schema.py` の `EVENT_TYPES` enum 現行値 | Read で確認。Gemini の `response_schema` enum と完全一致させる |
| `google-genai` SDK の正式 install 名 | `pip show google-genai` または PyPI で確認 |
| Gemini API キーの存在 | `AI-Pulse/.env` に `GEMINI_API_KEY=` があるか確認 |

### Step 1: 依存と環境（10 分）

1. `AI-Pulse/.gitignore` に `.env` を追加
2. `AI-Pulse/pyproject.toml` の `dependencies` に `google-genai>=1.0`, `trafilatura>=2.0`, `python-dotenv>=1.0` 追加
3. `pip install -e .` で venv に引き込み
4. `AI-Pulse/.env.example` を作成（中身は `GEMINI_API_KEY=your-key-here` のみ）。**実物 `.env` はユーザーが手で書く**

### Step 2: 新規モジュール（60-90 分）

1. `tools/rate_limiter.py`（トークンバケット・先に書いて契約テストで動作確認）
2. `tools/fetch_article.py`（resolve + extract・trafilatura 呼び出し）
3. `tools/llm_gemini.py`（Gemini API 薄ラッパ・response_schema 強制）
4. `prompts/gemini_summarize.md`（system_instruction + user テンプレ）
5. `tools/schema.py` から `response_schema` を export（`_validate_event_extras` と一致確認）
6. `tools/config.py` に新規定数追加（GEMINI_MODEL / GEMINI_RPM / ARTICLE_FETCH_TIMEOUT / MAX_BODY_CHARS / MIN_BODY_CHARS）

### Step 3: collect_rss.py 改造（30 分）

- `_fetch_rss` は維持
- `_make_event` を 2 段化:
  1. RSS dict の最低限を作る（title, link, source_name, date）
  2. `fetch_article.extract` → `llm_gemini.generate_event_extras` → 確定 dict
  3. `event_id` は `-gemNN` 接尾辞
  4. `source_url` は publisher 直リンク
  5. `_validate_event_extras` を ingest 前に呼んで違反は弾く
- `_score_and_importance` は Gemini に責務移管したため削除候補（コミットは残す方が安全・comment out でも可）

### Step 4: 契約テスト追加（45 分）

新規 5 件（`tests/test_llm_gemini.py` 3 件 + `tests/test_fetch_article.py` 2 件）。詳細は最終プランの Section 7。

| ファイル | テスト名 | 封じる class of bug |
| --- | --- | --- |
| `test_llm_gemini.py` | `test_schema_violation_retries_once` | Gemini が summary_points 2 件返す → 1 回再投げ → 4 件返す → ok |
| 同 | `test_rate_limit_blocks_until_token` | 13 req 目を 5 秒以上待たせる（突発バーストで 429 を防ぐ） |
| 同 | `test_failure_drops_candidate` | 3 回連続 5xx → ingest に None で届かない |
| `test_fetch_article.py` | `test_redirect_resolves_to_publisher` | モック HTTPServer で 302 → publisher URL |
| 同 | `test_short_body_drops` | text &lt; 200 字 → 例外 → ドロップ |

Mock は `unittest.mock` で十分（API キー不要・ネットワーク不要）。**既存 38 PASS は不変条件保護のため一切いじらない**。

### Step 5: 既存 RSS 95 件削除（15 分）

1. `scripts/purge_rss_events.py` を作成
2. `data/events.jsonl` と `data/entities.jsonl` を `.bak-YYYYMMDD` 接尾辞でコピー
3. `python scripts/purge_rss_events.py` 実行
   - `re.search(r"-rss\d+$", event_id)` 一致を削除（95 件）
   - `entities.jsonl` の 21 件すべてで `recent_events` 再計算・`snapshot_date` 更新
4. `wc -l data/events.jsonl` で 25 行・`grep -c -- "-rss" data/events.jsonl` で 0 を確認

### Step 6: 手動実行と E2E（30 分）

1. `python -m pytest -q` で **43 PASS**（38 既存 + 5 新規）
2. 1 entity 試走（例: claude-opus 1 件のみ）→ 標準出力で req 数・`skipped_extract`・`skipped_llm` を確認
3. `python tools/run_daily.py` を 1 回手動実行（13〜15 分待ち）
4. 件数確認: `wc -l data/events.jsonl` で 25 + 数十件
5. PWA cache bump: `static/sw.js` の `CACHE` を `aipulse-v6` に
6. `python -m generate_pages` で `site/` 再生成（呼び出し名は `tools/generate_pages.py` の main で確認）
7. `python -m http.server 5500 --directory site --bind 127.0.0.1` で配信
8. Chrome DevTools MCP で desktop 1280 + mobile 390 の E2E
   - 新 event カードに日本語 summary・summary_points 箇条書き・rationale 3 軸（展開）が出ているか
   - source link が publisher 直リンク（`https://news.google.com/` 始まりではない）か
   - モバイルで横はみ出し 0・console 0

### Step 7: 完了報告（5 分）

「pytest 43 PASS（38 既存 + 5 新規）・手動実行で新 events N 件追加・E2E で desktop/mobile 確認・横はみ出し 0・console 0」を実測値付きで報告（`feedback_test_before_report` 準拠）。

**Task Scheduler 切替（`scripts/run_daily.bat` の中身差し替え）は本セッションでもやらない**。それまでは朝 7:00 の自動実行が旧 RSS 方式のまま走るが、purge 実行後は新 events が積まれない期間が発生する点だけ留意。

---

## 6. 守るべき制約（前セッションで確定済）

- 既存 38 PASS を**一切いじらない**（不変条件保護）
- API キーを git に commit しない（`.env` は `.gitignore` 必須）
- Gemini の本文取得失敗（text &lt; 200 字 / タイムアウト）は当該記事ドロップ・RSS description フォールバックは**しない**（品質優先）
- score / importance / event_type は Gemini に任せる（Python ルールは復活させない）
- 手製 25 件の英文 → 日本語化は本実装スコープ外（次々セッション）
- コミットは明示 GO まで実施しない（`safe-commit` ゲート通過後）
- push は本セッションでも次セッションでもしない（不可逆・GO 待ち）

---

## 7. パラメータ（playground で確定する場合）

HTML 仕様書の playground を触ってから来た場合は、コピーされたプロンプトをそのまま使う。何も触らなかった場合は以下の default で `tools/config.py` を設定:

```python
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_RPM = 12              # 15 RPM の 20% 余裕代
GEMINI_TIMEOUT_SEC = 30
ARTICLE_FETCH_TIMEOUT = 12   # trafilatura/urllib タイムアウト
MAX_BODY_CHARS = 3000        # Gemini に渡す本文の最大文字数
MIN_BODY_CHARS = 200         # 短文はドロップ（paywall/404 対策）
SCORE_MIN = 50               # 既存値を維持
```

---

## 8. 関連 memory

- `project_ai_pulse`（追補 9 が本件の要約）
- `feedback_research_constraints_upfront`（Gemini Free Tier 制約を最初に明文化済）
- `feedback_no_speculation`（trafilatura の GNews redirect 挙動は実装前に Probe で確認・推測しない）
- `feedback_check_design_principles`（契約テスト 1 件で class of bug を封じる原則）
- `feedback_test_before_report`（完了報告前に 43 PASS + 実測値）
- `feedback_web_ui_e2e_test`（curl 確認だけでなく Chrome DevTools E2E まで）
- `feedback_japanese_env_first_scripting`（.env を扱う .ps1 / .py の文字コード規約）
- `reference_chrome_devtools_mcp`（E2E 検証用）

---

## 9. 次セッション開始時にユーザーが貼るプロンプト（テンプレ）

下記をそのまま次セッション冒頭でユーザーが貼り付ければよい:

```
AI-Pulse 収集パイプライン再設計の実装を始めます。

最初に読むファイル（順番に）:
1. AI-Pulse/docs/handoff_2026-06-03_pipeline_redesign.md（本引継ぎ書）
2. C:\Users\hidek\.claude\plans\ai-pulse-wise-tide.md（最終プラン）
3. AI-Pulse/docs/specs/2026-06-03_collection-pipeline-redesign.html（HTML 仕様書）

Gemini API キーは AI-Pulse/.env の GEMINI_API_KEY に書いてあります（または冒頭で渡します）。
Section 5 の Step 0〜7 の順で進めて、Step 6 の E2E まで完走したら報告してください。
Task Scheduler 切替（run_daily.bat の中身差し替え）は別セッションなので本セッションでは絶対にやらないでください。

既存 38 契約テスト PASS を一切いじらず、新規 5 件を追加して 43 PASS が完了条件です。
```

`.env` を事前に書かない場合は最後の段落を「Gemini API キーは XXXX です」に差し替える。

---

## 10. 補足: 設計セッションで除外された案（参考）

| 案 | 除外理由 |
| --- | --- |
| 速報ジョブ復活（`claude -p` WebSearch） | `claude -p` / `claude --print` が将来 Anthropic 課金扱いになる前提 |
| News-Grasp の `claude --print` 経路をそのまま流用 | 同上 |
| anthropic SDK 直呼び（Haiku 4.5） | $0.2/日 と安価だが Capstone の MCP 採用思想（API 課金回避）と相反 |
| NotebookLM へ統一 | fast モード 1〜3 分/件 × 95 = 数時間で速報不向き |
| LLM 完全不使用（rule-based） | 事実抽出に限定され手製 25 件の品質に及ばない |
| Ollama ローカル LLM（RTX 5080） | 課金完全ゼロだが品質安定性と運用負荷で Gemini Flash に劣る |
| 現状維持 + 手製優先表示 | 低品質 RSS が残る = 根本見直しになっていない |

これらは次セッションで「やっぱり別案で…」と揺り戻ししないよう、設計コストを燃焼済の確定除外として記録。再検討する場合は明確な根拠（claude -p 課金化が実は無い・Capstone 思想が変わった等）を添えて議論する。
