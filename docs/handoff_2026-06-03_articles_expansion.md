# 引継ぎ: AI-Pulse の記事増加と残タスク検討（2026-06-03 作成）

次セッションの主題は **「現状3記事しかない掲載を増やしていく」**。本書はそのための現状整理・構造的な論点・判断ポイント・具体的な操作手順・残タスクを1か所にまとめたもの。**まず本書と一次ソース仕様書 `docs/specs/2026-06-02_ai-pulse-architecture.html` を読んでから着手すること**（このリポジトリはローカルなのでファイル参照可）。

---

## 1. いまの状態（事実）

| 項目 | 値 |
| --- | --- |
| 掲載記事（L2 events） | **3件**（`data/events.jsonl`・model/editor/media 各1） |
| エンティティ・カルテ（L1） | **3件**（`data/entities.jsonl`・claude-opus / cursor / flux） |
| カテゴリ（レンズ） | **7**（model / editor / **physical** / media / agent / infra / policy。physical は 2026-06-03 追加） |
| physical（フィジカルAI）のデータ | **0件**（枠・色・グリフ・比較軸・サムネのみ。記事もカルテも無い） |
| Git | private repo `HIDEPON-UMG/AI-Pulse` の `origin/master` に3コミット push 済（最新 `161b6af`） |
| 収集パイプライン | **設計・契約テスト済だが “ライブ運用” は未実施**。現3件は手作りのデモデータを実在ニュースに整えたもの |

**最重要の前提**: 記事が増えないのは実装バグではなく **運用がまだ走っていない**から。パイプライン自体は出来ている。

---

## 2. なぜ記事が増えないのか（構造を理解してから動く）

データは2層で、収集も2ジョブに分かれている（`docs/specs` の「データフロー」タブ参照）。

- **速報ジョブ**（`prompts/breaking_websearch.md` → `tools/research_websearch.py`）
  - `claude -p`（ヘッドレス）が7レンズを WebSearch → L2 events を下書き → Python が検証・閾値・重複排除・永続化。
  - **制約（ここが効く）**: 速報ジョブは **既知エンティティに紐づくニュースしか採用しない**。未知の対象の新規カルテは作らない（それは深掘りジョブの責務）。
  - つまり **カルテ（entities）が3つしかない限り、速報で増える記事もその3社の周辺に限られる**。
- **深掘りジョブ**（`prompts/deepdive_notebooklm.md` → `tools/research_notebooklm.py`）
  - NotebookLM の deep research で **カルテ（L1）を最新化／新規作成**する非同期2段（kick → collect → apply）。
  - **新しいプレイヤーをサイトに載せるには、まずここでカルテを増やす必要がある**。

→ 記事を増やす本質は **「カルテ（取り上げる企業・製品）を増やす」＋「速報を回してイベントを積む」** の両輪。今は physical を筆頭に空きレンズが多い。

---

## 3. 記事を増やす選択肢（ユーザーと方針を決める）

着手前に、以下のどれで進めるかを**必ずユーザーに確認する**（粒度・運用コストが大きく変わるため）。

| 案 | 内容 | 向き / コスト |
| --- | --- | --- |
| **A. 手動シード**（まず推奨の足場） | physical 等の空きレンズに **カルテを数件ハンドオーサリング**（公式URLで裏取り）→ 速報を1回手動実行してイベントを積む | 即効・少量。捏造ゼロで質を担保しやすい。まず数を作って画面を埋める |
| **B. 速報ジョブを実運用** | `claude -p` で `breaking_websearch.md` を回し既知カルテ周辺のイベントを継続収集 | カルテが揃ってから効く。Aの後段 |
| **C. 深掘りジョブで新カルテ量産** | NotebookLM deep research で新規プレイヤーのカルテを増やす | 取り上げ範囲の拡大本体。レイテンシ deep 5–30分・非同期 |
| **D. Step7 自動化** | A〜Cを Task Scheduler ＋ `claude -p` で定期実行（速報＝短周期／深掘り＝長周期） | 恒久運用。**外部実行・不可逆寄りなので GO 必須**。[[reference_cowork_network_sandbox]] のとおり定期収集は Cowork 不可・ホストCLIが正解 |

**おすすめの順序**: まず **A（手動で physical 含む空きレンズにカルテを数件シード）→ 画面の見栄えを確認 → B/C で増やす → 安定したら D で自動化**。いきなり D に行かない。

---

## 4. 着手前にユーザーへ確認すべき判断ポイント

1. **どのレンズ・どの企業/製品を優先するか**（physical は空。例: ヒューマノイド系 Figure / Tesla Optimus / Physical Intelligence、ロボット基盤モデルの VLA 系など。ただし**実在・公式ソースで裏取りできるものだけ**）。
2. **当面の目標件数**（例: 各レンズ最低2カルテ／フィード15件、など）。
3. **収集の主体**: 当面は手動（A）で良いか、すぐ自動化（D）まで行くか。
4. **公開タイミング**: 記事を増やしてから GitHub Pages 公開（private→public 判断）に進むか。

---

## 5. 具体的な操作（コマンド・ファイル・パラメータ）

### データを足す
- カルテ（L1）: `data/entities.jsonl` に1行追記。必須フィールドは `tools/schema.py` の `ENTITY_REQUIRED`。比較表を付けるなら所属レンズの `LENS_AXES` の全 axis を埋める（穴あき禁止＝schema が弾く）。physical の軸は `form / hardware / foundation / autonomy / strength`。
- 記事（L2）: `data/events.jsonl` に1行追記。必須は `EVENT_REQUIRED`＋`_validate_event_extras`（`source_url`=http / `karte_updated`=bool / `summary_points`=3–5 / `rationale`={importance,impact,buzz}）。`category` は7レンズの enum 内（`physical` 可）。

### ビルド・検証・配信
```
python tools/generate_pages.py                 # site/ に index/archive/karte 生成
python -m pytest -q                            # 契約テスト（現在 38 PASS が基準）
python -m http.server 5500 --directory site --bind 127.0.0.1   # ローカル配信（8765/8771 は Hyper-V 予約で WinError10013）
```
完了報告の前に **pytest 実行＋実機（Chrome DevTools, desktop と mobile 390px）で console0・横はみ出し0** を確認する（[[feedback_test_before_report]] / [[feedback_web_ui_e2e_test]]）。アセットを変えたら **`static/sw.js` の `CACHE` を bump**（現在 `aipulse-v4`。[[reference_safe_commit_skill]] ゲート6）。

### パイプラインを回す（B/C を選んだ場合）
- 速報: `prompts/breaking_websearch.md` の手順どおり `claude -p` で下書き→`python tools/research_websearch.py candidates.json`。
- 深掘り: `prompts/deepdive_notebooklm.md` の段A（`kick_deep`）→ 段B（`collect`→`apply_deepdive`）。`RECHECK_DAYS`/`DEEP_POLL_MINUTES`/`BREAKING_PER_CATEGORY`/`SCORE_MIN` は `tools/config.py`。

---

## 6. 守る制約（質を落とさないための既定）

- **捏造禁止**: 日付・数値・出典は**実在を公式/一次ソースで裏取り**してから載せる。裏取りできない URL は付けない（年止まり可）。定量値は `tools/verify_quant.py` の `verify(値, source_url)` 相当で False なら本文から落とす。
- **NotebookLM は公開情報のみ**（機密送信禁止・速報には不向き＝fast 2–5分/deep 5–30分）。
- **配色・デザインは `DESIGN.md` が単一ソース**。色・フォント・余白を直書きしない（`var(--cat)` 等トークン参照）。新レンズ色は DESIGN.md にも追記（physical は追補7 で同期済）。
- **日本語**で会話・コメント・ドキュメント。
- コミット/push は **明示指示時のみ**、`safe-commit` 6ゲートを通す。push は default branch 保護を勝手に回避しない。

---

## 7. 記事増加以外の残タスク（棚卸し）

| 優先 | タスク | メモ |
| --- | --- | --- |
| 🟡 | **physical のデータ投入** | 追加した枠が空。記事増加タスクの一部として最優先で1件目を入れたい |
| 🟡 | ロゴ意匠の目視評価 | パルス線＋ニューロン節点＋シナプス枝。別モチーフへ振り直し可 |
| 🟡 | 関係性（relations）の出典URL | `since`/`models` は公開情報で補完済だが**出典URL未付与**。curl 実在確認してから追加 |
| 🟢 | 競合比較の `{name}=本エンティティ` 脚注 | 別ブロックで残置。消すかは好み |
| 🟢 | index.html.j2 onclick の `source_url` JS文字列埋込 hardening | 既知軽微・非exploitable（静的＋curate済＋`startswith("http")`）。`data-href`＋delegated handler 化が筋。直したら click E2E 再検証 |
| ⏸️ | **GitHub Pages 公開** | 外部公開・不可逆・**GO待ち**。private→public 化判断／方式 docs vs Actions／フォント self-host 要否が未決 |
| ⏸️ | Step7 Task Scheduler（速報・深掘りの2系統） | 自動運用（案D）。**GO待ち** |
| ⏸️ | ClaudeCodeFeed 撤去 | 不可逆・GO待ち |

---

## 8. 次セッションの始め方

冒頭でこう声がけすればよい（例）:

> 「AI-Pulse の続き。`docs/handoff_2026-06-03_articles_expansion.md` を読んで、記事増加の方針（案A〜D）を提示してから着手して。」

関連 memory: `project_ai_pulse`（プロジェクト状態の一次ソース）・`feedback_research_constraints_upfront`・`feedback_no_speculation`・`feedback_test_before_report`・`feedback_web_ui_e2e_test`・`reference_cowork_network_sandbox`（定期収集はホスト CLI が正解）・`reference_notebooklm_digest`。

> 注: 本ファイルは未コミット。次セッションで記事増加の最初のコミットに同梱するか、不要なら削除してよい。
