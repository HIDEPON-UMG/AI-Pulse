# 引継ぎ: AI-Pulse の記事増加と残タスク（2026-06-03 更新）

次セッションの主題は **「21カルテに紐づく記事（events）を速報パイプラインで増やし、ライブ運用を開始する」**。
本書はそのための現状整理・構造的な論点・判断ポイント・具体的な操作手順・残タスクを1か所にまとめたもの。
**まず本書と一次ソース仕様書 `docs/specs/2026-06-02_ai-pulse-architecture.html` を読んでから着手すること**（このリポジトリはローカルなのでファイル参照可）。

---

## 1. いまの状態（事実）

| 項目 | 値 |
| --- | --- |
| 掲載記事（L2 events） | **25件**（`data/events.jsonl`） |
| エンティティ・カルテ（L1） | **21件**（`data/entities.jsonl`） |
| カテゴリ（レンズ） | **7**（model / editor / physical / media / agent / infra / policy） |
| overview フィールド | **全21件に追加済**（positioning 直下に 3〜5 文の説明文） |
| Git | private repo `HIDEPON-UMG/AI-Pulse` の `origin/master` に push 済（最新コミット参照） |
| 収集パイプライン | **設計・契約テスト済だが "ライブ運用" は未実施**。現25件は手作りのデモデータを実在ニュースに整えたもの |

**カルテ内訳（2026-06-03 時点）:**

| レンズ | entity_id 一覧 |
| --- | --- |
| model（6件） | claude-opus / qwen / deepseek / gemini / llama |
| model（続き） | ※ GPT 系は未追加（見送り） |
| editor（3件） | cursor / windsurf |
| physical（3件） | physical-intelligence / figure / tesla-optimus |
| media（2件） | flux / runway |
| agent（4件） | devin / agentkit / dify / langgraph |
| infra（3件） | vera-rubin / ironwood-tpu / cosmos |
| policy（2件） | eu-ai-act / japan-ai-act |

**最重要の前提**: 記事が少ないのは実装バグではなく **運用がまだ走っていない**から。パイプライン自体は出来ている。

---

## 2. なぜ記事が増えないのか（構造を理解してから動く）

データは2層で、収集も2ジョブに分かれている（`docs/specs` の「データフロー」タブ参照）。

- **速報ジョブ**（`prompts/breaking_websearch.md` → `tools/research_websearch.py`）
  - `claude -p`（ヘッドレス）が7レンズを WebSearch → L2 events を下書き → Python が検証・閾値・重複排除・永続化。
  - **制約**: 速報ジョブは **既知エンティティに紐づくニュースしか採用しない**。
  - カルテが21件になったため、速報を回せば各エンティティの最新イベントを継続収集できる。
- **深掘りジョブ**（`prompts/deepdive_notebooklm.md` → `tools/research_notebooklm.py`）
  - NotebookLM の deep research で **カルテ（L1）を最新化／新規作成**する非同期2段。
  - 新規プレイヤーをサイトに載せるにはこのジョブでカルテを増やす。

→ 現状の最優先は **B. 速報ジョブを実運用** して21カルテ分のイベントを積むこと。
  カルテはすでに揃っているため速報が最も即効性が高い。

---

## 3. 記事を増やす選択肢（ユーザーと方針を決める）

着手前に以下のどれで進めるかを**必ずユーザーに確認する**（粒度・運用コストが大きく変わるため）。

| 案 | 内容 | 向き / コスト |
| --- | --- | --- |
| **A. 手動シード（補完）** | 既存21カルテの各1件イベントを手動で追加し情報を充実させる | 即効・品質高・捏造リスク低。各カルテに最低2〜3件欲しい段階 |
| **B. 速報ジョブを実運用** ★最優先 | `claude -p` で `breaking_websearch.md` を回し21カルテ周辺のイベントを継続収集 | カルテが揃ったので今すぐ効く。まずここ |
| **C. 深掘りジョブで新カルテ量産** | NotebookLM deep research で新規プレイヤーのカルテを増やす | 取り上げ範囲の拡大本体。レイテンシ deep 5–30分・非同期 |
| **D. Step7 自動化** | B〜Cを Task Scheduler ＋ `claude -p` で定期実行 | 恒久運用。**外部実行・不可逆寄りなので GO 必須**。定期収集はホスト CLI が正解（[[reference_cowork_network_sandbox]]） |

**おすすめの順序**: まず **B（速報を1回手動実行）→ 記事を確認 → A で補完 → D で自動化**。

---

## 4. 着手前にユーザーへ確認すべき判断ポイント

1. **速報ジョブの実行タイミング**: すぐ B を回すか、A（手動補完）を先に進めるか。
2. **新規カルテの優先度**: 見送り中の GPT / OpenAI o シリーズ / ComfyUI 等を追加するか。
3. **GitHub Pages 公開タイミング**: 記事が一定数（例: フィード 50件）揃ってから公開か、先に公開か。
4. **日次バッチの間隔**: 速報を何時間おきに回すか（API コスト・情報鮮度のトレードオフ）。

---

## 5. 具体的な操作（コマンド・ファイル・パラメータ）

### データを足す（手動）

- カルテ（L1）: `data/entities.jsonl` に1行追記。必須フィールドは `tools/schema.py` の `ENTITY_REQUIRED`。比較表を付けるなら所属レンズの `LENS_AXES` の全 axis を埋める（穴あき禁止＝schema が弾く）。
- **overview フィールド（新規追加済）**: `positioning` の直下に 3〜5 文の説明文。optional だが全件あること推奨。`**太字** / ==マーカー== / __下線__` の強調記法が使える。
- 記事（L2）: `data/events.jsonl` に1行追記。必須は `EVENT_REQUIRED`＋`_validate_event_extras`（`source_url`=http / `karte_updated`=bool / `summary_points`=3–5 / `rationale`={importance,impact,buzz}）。

### ビルド・検証・配信

```bash
python tools/generate_pages.py                 # site/ に index/archive/karte 生成
python -m pytest -q                            # 契約テスト（現在 38 PASS が基準）
python -m http.server 5500 --directory site --bind 127.0.0.1   # ローカル配信
```

完了報告の前に **pytest 実行＋実機（Chrome DevTools, desktop と mobile 390px）で console0・横はみ出し0** を確認する。アセットを変えたら **`static/sw.js` の `CACHE` を bump**（現在 `aipulse-v4`）。

### パイプラインを回す（B 速報ジョブ）

- `prompts/breaking_websearch.md` の手順どおり `claude -p` で下書き→`python tools/research_websearch.py candidates.json`。
- 深掘り: `prompts/deepdive_notebooklm.md` の段A→段B。`RECHECK_DAYS`/`DEEP_POLL_MINUTES`/`BREAKING_PER_CATEGORY`/`SCORE_MIN` は `tools/config.py`。

---

## 6. 守る制約（質を落とさないための既定）

- **捏造禁止**: 日付・数値・出典は**実在を公式/一次ソースで裏取り**してから載せる。新10カルテのイベントは手作りデモデータ（公式URLで裏取り済）。速報ジョブ追加分は `verify_quant.py` を通す。
- **NotebookLM は公開情報のみ**（機密送信禁止・速報には不向き）。
- **配色・デザインは `DESIGN.md` が単一ソース**。色・フォント・余白を直書きしない（`var(--cat)` 等トークン参照）。
- **日本語**で会話・コメント・ドキュメント。
- コミット/push は **明示指示時のみ**、`safe-commit` 6ゲートを通す。

---

## 7. 残タスク一覧（棚卸し）

| 優先 | タスク | メモ |
| --- | --- | --- |
| 🔴 P0 | **速報ジョブのライブ運用開始** | 21カルテ分のイベントが1件しかない状態。`claude -p` で `breaking_websearch.md` を回す |
| 🟡 P1 | 各新カルテへのイベント追加（手動補完） | 新10カルテは各1件のみ。2〜3件に増やして比較カルテとして見応えを出す |
| 🟡 P1 | GitHub Pages 公開判断（private→public） | フィード件数・カスタムドメイン・フォント self-host 要否が未決 |
| 🟡 P1 | ロゴ意匠の目視評価 | パルス線＋ニューロン節点＋シナプス枝。別モチーフへ振り直し可 |
| 🟡 P1 | 関係性（relations）の出典 URL | `since`/`models` は公開情報で補完済だが**出典 URL 未付与**（一部エンティティ） |
| 🟢 P2 | Step7 Task Scheduler（速報・深掘り2系統） | 自動運用（案D）。**GO待ち** |
| 🟢 P2 | onclick source_url JS hardening | 既知軽微・非 exploitable。`data-href`＋delegated handler 化が筋 |
| ⏸️ | ClaudeCodeFeed 撤去 | 不可逆・GO待ち |

---

## 8. 次セッションの始め方

冒頭でこう声がけすればよい:

> 「AI-Pulse の続き。`docs/handoff_2026-06-03_articles_expansion.md` を読んで、今の状態（21カルテ・25イベント）を把握してから、速報ジョブを1回手動実行して記事を増やす作業を進めて。」

関連 memory: `project_ai_pulse`（プロジェクト状態の一次ソース）・`feedback_research_constraints_upfront`・`feedback_no_speculation`・`feedback_test_before_report`・`feedback_web_ui_e2e_test`・`reference_cowork_network_sandbox`（定期収集はホスト CLI が正解）・`reference_notebooklm_digest`。
