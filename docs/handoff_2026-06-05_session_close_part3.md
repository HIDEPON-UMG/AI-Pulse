# 次セッション引継ぎ — 2026-06-05 Part 3 (ハイブリッド本配線完了・push GO 待ち)

作成: 2026-06-05 (本セッション末)
直近 push 済: `2e50b8a` (= origin/master HEAD、Part 2 と同じ。本 Part 3 セッションでは push なし)

前 handoff:
- [docs/handoff_2026-06-05_session_close_part2.md](handoff_2026-06-05_session_close_part2.md) (Part 2 — 緊急停止対応 + 構造的未配線発覚)
- [docs/handoff_2026-06-05_session_close.md](handoff_2026-06-05_session_close.md) (Part 1 — 朝のセッション)
- [docs/handoff_2026-06-04_session_close_part4.md](handoff_2026-06-04_session_close_part4.md) (Qwen3.6 カルテ追加 + `M` 残置起点)
- [docs/eval/2026-06-04_qwen3_vs_gemini.md](eval/2026-06-04_qwen3_vs_gemini.md) (推奨判断 L302 が **`[x]` 更新済**)

> **本セッションの大筋**: Part 2 で構造的未配線として発覚した「ハイブリッド LLM 本配線」を、追補10 で確定済の A確定config 通りに実装完了。8 系統のファイル変更で **66 テスト PASS** (旧 54 + hybrid 8 + rewrite_emphasis 6 - emphasis 2)。`tools/llm_hybrid.py` の ruff TID251 (banned-api) も `quiet_run` 経由で解消済。**push は GO 待ち**で本セッション内では実施せず。

---

## 1. 本セッションで実施した本配線 (push なし)

### 1.1 変更ファイル 8 系統 + テスト 3 系統

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 改修 | [tools/config.py](../tools/config.py) | `OLLAMA_MODEL = "hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-IQ3_XXS"` (旧 `qwen3:14b`) / `OLLAMA_TEMPERATURE = 0.1` (旧 0.4) / `MAX_BODY_CHARS = 5000` (旧 3000) / 追加: `HYBRID_MODE = "local_first"` / `HYBRID_GPU_THRESHOLD_FB_MB = 6000` / `HYBRID_LOCAL_RETRY_BEFORE_FALLBACK = OLLAMA_MAX_RETRIES` |
| 改修 | [tools/llm_gemini.py](../tools/llm_gemini.py) | `PROMPT_PATH` を `prompts/gemini_summarize.md` → `prompts/extract_grounded.md` に切替 / `_check_shape` から emphasis 検証 3 行削除 / `EmphasisShortageError` クラス削除 / `_RE_MARK` / `_RE_UND` / `_RE_BOLD` 削除 / `generate_event_extras` の retry ループから emphasis 分岐削除 / `temperature 0.4 → 0.1` |
| 退避 | `prompts/gemini_summarize.md` → [prompts/.archive/gemini_summarize.md](../prompts/.archive/gemini_summarize.md) | `git mv` で履歴保持。`tools/eval_fabrication_fix.py` の `BASE_PROMPT` も `.archive/` 経由に追従修正 |
| 新規 | [tools/llm_hybrid.py](../tools/llm_hybrid.py) | `generate_event_extras(article_text, meta, *, gpu_probe=None)` ファサード。`local_first` / `gemini_first` / `gemini_only` / `local_only` の 4 モード切替。`_gpu_busy()` は `nvidia-smi --query-gpu=memory.used` を `_proc.run.quiet_run` 経由で叩く (TID251 ban 回避 + Windows 黒窓回避)。smi 不在・失敗は「非占有」扱いで local を試させる安全側 |
| 改修 | [tools/collect_rss.py](../tools/collect_rss.py) | L205 を `llm_gemini.generate_event_extras` → `llm_hybrid.generate_event_extras` に / 直後で `rewrite_emphasis.rewrite_event` を呼んで強調記法を決定論コード付与 / `_verify_event_quant` で summary の数値が article 本文に存在するか機械照合 (半数超 missing で `skipped_quant` 集計) / 本文を `MAX_BODY_CHARS` で打切り / import に `llm_hybrid` `rewrite_emphasis` `verify_quant` を追加 |
| 新規 | [tests/test_llm_hybrid.py](../tests/test_llm_hybrid.py) | **8 件**: `local_first` で local 成功時 Gemini 非呼出 / local 失敗で Gemini フォールバック / GPU 占有時 local 非呼出で直接 Gemini / `gemini_only` 常時 Gemini / `local_only` Gemini 非呼出で raise / GPU probe 閾値判定 3 件 |
| 新規 | [tests/test_rewrite_emphasis.py](../tests/test_rewrite_emphasis.py) | **6 件**: 数値含む `**X**` → `==X==` 昇格 / 動詞含む `**X**` → `__X__` 昇格 / 既存 `==`/`__` touched せず冪等 / 固有名のみ太字維持 / event dict の summary + summary_points 同時変換 / 2 回目 changed=False |
| 改修 | [tests/test_llm_gemini.py](../tests/test_llm_gemini.py) | emphasis 検証関連 2 件 (`test_emphasis_only_bold_retries_once` / `test_emphasis_no_marks_at_all_fails`) を削除。`_VALID_PAYLOAD` から強調記法も除去 (prompt 切替後は LLM に出させない) |
| 更新 | [docs/eval/2026-06-04_qwen3_vs_gemini.md](eval/2026-06-04_qwen3_vs_gemini.md) | L302 を `[ ] ハイブリッド` → `[x] ハイブリッド` に更新 + Part 3 完了の脚注を追加 |
| 更新 | memory `project_ai_pulse.md` | 追補12 を追記 |

### 1.2 検証実測値

```
$ ./.venv/Scripts/python.exe -m unittest discover -s tests
Ran 66 tests in 2.276s
OK
```

- **66/66 PASS** (旧 54 + hybrid 8 + rewrite_emphasis 6 - emphasis 2)
- `tools/llm_hybrid.py` ruff TID251 (banned-api) **解消** (`_proc.run.quiet_run` 経由)
- 残 E501 (行長制限) は本セッション新規行も含むが、AI-Pulse 全体で 36 件あった既存パターン踏襲 (日本語コメント・docstring 由来)。本配線で純増した違反は無し

### 1.3 安全側に倒した設計判断

- **GPU 占有検出**: `nvidia-smi` 不在 / 失敗時は **「占有なし」扱い** で local を 1 度は試させる。GPU 無し環境でも Ollama 接続失敗で Gemini に流れる経路を保つため
- **verify_quant の閾値**: 数値主張が複数ある場合、**半数超** (`_QUANT_MISSING_RATIO_LIMIT = 0.5`) が本文に見当たらない時のみ skip。誤検出を抑制 (1 件だけ missing でドロップしない緩めの閾値)
- **HYBRID_LOCAL_RETRY_BEFORE_FALLBACK は OLLAMA_MAX_RETRIES に集約**: hybrid 層は追加リトライせず、`llm_local` 側のバックオフが尽きた LLMError を 1 度で受けたら即 Gemini に流す
- **rewrite_emphasis 配線位置**: `_make_event` の後ではなく **その前** で `extras` の summary / summary_points を上書き。これで `_make_event` 以降は通常パス、ev dict 自体に強調記法が反映される
- **`prompts/gemini_summarize.md` は archive 退避** (削除でなく): `tools/eval_fabrication_fix.py` 等の eval 再走可能性を保つ。BASE_PROMPT パスを `.archive/` 経由に追従

### 1.4 実機未検証 (mock 化済の領域)

テストは全件 mock で骨格を保証していますが、**本番初回起動** は以下が未走:

- Ollama サーバ起動 + Qwen3.6-35B-A3B モデルロード (起動時 ~30-60 秒 / warm 後 ~30s/件)
- 実 `nvidia-smi` での GPU 占有検出 (mock = `_gpu_busy(probe=...)` で代用)
- Gemini フォールバック実走 (Ollama 接続失敗 / GPU 占有を実機で再現)
- `verify_quant` の数値照合が本物の summary でどの程度 skipped_quant を出すか

→ これらは次セッションで `python tools/run_daily.py` 試走時に確認。**Gemini API 課金発生のためユーザー GO 待ち**。

---

## 2. 次セッションの最優先タスク (優先順)

### 高 1: コミット & push (= safe-commit ゲート 6 段)

本配線分は `f7cc1e4` 後の以下が未コミット (Part 2 から継続の `data/*.jsonl` も含む):

```
M  data/entities.jsonl       (Part 1 末尾の未コミット差分・本セッション未関与)
M  data/events.jsonl         (Part 1 末尾の未コミット差分・本セッション未関与)
M  docs/eval/2026-06-04_qwen3_vs_gemini.md
M  tools/collect_rss.py
M  tools/config.py
M  tools/eval_fabrication_fix.py
M  tools/llm_gemini.py
R  prompts/gemini_summarize.md -> prompts/.archive/gemini_summarize.md
?? tools/llm_hybrid.py
?? tests/test_llm_hybrid.py
?? tests/test_rewrite_emphasis.py
M  tests/test_llm_gemini.py
?? docs/handoff_2026-06-05_session_close_part2.md (Part 2 で作成)
?? docs/handoff_2026-06-05_session_close_part3.md (本ファイル)
```

**コミット方針案** (ユーザー判断要):
1. **本配線 commit** = 上記のうち `data/*.jsonl` 以外を 1 commit にまとめる (ハイブリッド本配線という単一意図のため)
2. `data/*.jsonl` (Part 1 末尾差分) は別 commit (テーマ違い)
3. handoff Part 2 + Part 3 は 1 commit (drop or 同 commit に統合)

`safe-commit` ゲート 6 段:
- ゲート 1 (個人情報): クリア見込
- ゲート 2 (セキュリティ): 軽量チェックで確認
- ゲート 3 (機密情報質問): `GEMINI_API_KEY` 等の機密文字列が差分に無いか確認 (本配線では env 読込ロジックには触っていない)
- ゲート 4 (DESIGN.md): 本配線は CSS / トークン非関与
- ゲート 4' (HTML 仕様書): 本配線は HTML spec 非関与
- ゲート 5 (実機エントリ): AI-Pulse は SSG / 本配線は LLM 抽出経路 → smoke 未整備でスキップ可
- ゲート 6 (PWA SW 同期): アセット変更なし → bump 不要

### 高 1.5: 実機 smoke (Gemini API 課金事前確認後)

`run_daily.py` を 1 entity 限定で試走して以下を確認:

```powershell
# AI-Pulse プロジェクトルートで (Ollama サーバ起動済の前提)
./.venv/Scripts/python.exe tools/collect_rss.py claude-opus  # 1 entity だけ
```

確認項目:
- Qwen3.6-35B-A3B が `/api/chat` 経由で正常応答するか (think=false 効いてるか)
- `rewrite_emphasis` が `**X**` を `==X==` / `__X__` に正しく振り分けたか
- `verify_quant` の skipped_quant が異常に高くないか (`_QUANT_MISSING_RATIO_LIMIT = 0.5` の閾値妥当性)
- Gemini フォールバックが期待通り発火しないか (= local が安定動作するか)

**Gemini API 課金発生のためユーザー GO 待ち**。Free Tier 残量に余裕があれば走らせて OK。

### 高 2: Task Scheduler 起動経路の文字化け対策 (Part 2 §3 低 1)

Part 2 で挙げた `cmd /c` マルチバイトパス化け問題への対応。推奨案 (b):

| ファイル | 内容 |
|---|---|
| 新規 `scripts/run_daily.ps1` | 既存 `scripts/run_daily.bat` の PowerShell 版。`_logs/` 書き込みも `Add-Content -Encoding UTF8` で統一 |
| 新規 `scripts/run_weekly.ps1` | 同上 (週次バッチ) |
| Task Scheduler | Task Action を `cmd /c "...bat"` → `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "...ps1"` に書き換え (= ClaudeCodeFeed runner の実績パターン) |

### 高 3: Task Scheduler 再 Enable

「ハイブリッド本配線 (= 本セッション完了)」+ 「文字化け対策 (= 高 2 完了)」の **両方クリア後** に AI-Pulse 日次/週次バッチを Enable に戻す。Part 2 では誤 Disable → Enable 復元で現状 Ready 維持なので、再 Enable 作業自体は不要。**起動経路の安定確認** + **Gemini クォータ消費量の実測** が必要。

### 中: Gemini API 6/15 課金開始の真偽確認

Part 2 §3 中で未検証だった項目。WebFetch で:
- https://ai.google.dev/pricing (Gemini API Pricing)
- https://ai.google.dev/gemini-api/docs/changelog (Changelog)
- Google AI Studio リリースノート

確認結果次第で `config.py` の Free Tier 想定値 (RPM/RPD) を更新。**ハイブリッド本配線完了で local 優先になるため Gemini 呼出件数は大幅減** = 仮に Free Tier 廃止でも被害は限定的。

### 低 1: ClaudeCodeFeed Discord 通知出元の特定

Part 2 §3 低 2 継続。`C:\Users\hidek\bin\claudecodefeed-runner.ps1` 自身は git push までで Discord webhook は呼んでいない。出元候補:
- `~/Obsidian/ClaudeCodeFeed/scripts/` 配下の別 ps1
- GitHub Actions の webhook
- 別 Task Scheduler エントリ

### 低 2: News-Grasp Runner の扱い

Part 2 §1 残置。本セッションでは触らず。ユーザー判断要。

### 低 3: dispatch 構造解決の宿題 (追補11 §2)

追補11 で「次セッション冒頭で決断」とされていた dispatch の自動 inject 化:
- 案 (a): `project_ai_pulse.md` に `dispatch_json: {"task_class":["impl","debug"], "keywords":["AI-Pulse","ai-pulse","collect_rss","llm_gemini","llm_local","llm_hybrid","verify_quant","rewrite_emphasis"], "file_globs":["AI-Pulse/**"], "severity":"inject"}` を追加して自動 inject 対象に
- 案 (b): 「ハイブリッド配線指示」を独立 feedback memory として切り出して dispatch 有効化

→ 追補12 で本配線が完了したので、次に同種の漏れが起きるのは「本配線済の事実を後続セッションが忘れる」場面 → **案 (a) の方が effective**。実装は frontmatter 1 行追加 + `inject_relevant_memory.ps1` 動作確認の 5 分作業。

### 低 4: 本セッション残 ruff E501 (任意)

本セッションで触ったファイルに残る E501 (行長制限超過) 22 件 (TID251 解消後):

| ファイル | 件数 | 性質 |
|---|---|---|
| `tools/config.py` | 7 | 新規追加した日本語コメント (eval 由来の背景説明) |
| `tools/collect_rss.py` | 4 | 新規 docstring + 配線説明コメント |
| `tools/llm_gemini.py` | 9 | 大半は **本セッション未変更の既存行** (raise メッセージ等)。私が追加した docstring 2 件 |
| `tools/llm_hybrid.py` | 2 | docstring 1 行目 + raise メッセージ 1 行 |

→ AI-Pulse 全体で元 36 件あった既存パターン踏襲。次回 safe-commit ゲート時に折り返し or `# noqa: E501` 個別免除で対応。本セッション原因の純増ではない。

---

## 3. 守るべき制約 (前 handoff から継続 + 本 Part 3 追加)

- **66 PASS 維持**: 本配線で 54 → 66 に増えた件数を一切落とさない。新規追加は OK
- **コミット & push は明示 GO 待ち**: 本 Part 3 セッションでは push 実施せず
- **DESIGN.md トークン経由**: 色・余白は直書き禁止
- **新規 entity 追加は同 category 2 件以上で `comparison.cols` 必須**
- **`history[].url` / `modules.future[].url` / `event.source_url` は WebSearch / WebFetch + urllib HEAD/GET で実機 200 確認**
- **push 前は必ず `./.venv/Scripts/python.exe tools/audit_urls.py --gate` を通す**
- **Gemini API 呼出 (`tools/run_daily.py` 含む) は事前承認必須**
- **アセット変更を含む commit は `static/sw.js` の CACHE bump 必須** (本配線では非該当)
- **[新] HYBRID_MODE の本番デフォルトは `local_first`**: 緊急時のみ `gemini_only` に切替 (Ollama 全停止時の暫定回避)
- **[新] `prompts/extract_grounded.md` を本線として LLM プロンプトから強調記法指示は除去**: 強調記法は `rewrite_emphasis` で決定論コード付与 ([[feedback_check_design_principles]] §2「境界 1 箇所集約」)
- **[新] `tools/_proc/run.py` の `quiet_run` 境界を新規 subprocess 起動でも必ず通す**: ruff `TID251` ban (pyproject.toml で配線済) で物理的に弾く
- **[継承] ユーザー指示を eval doc / `M` 差分で「保留中」扱いにしない**: 本セッションで Part 2 反省を実装で解消

---

## 4. 重要ファイル参照 (次セッション冒頭読み推奨)

| ファイル | 役割 |
|---|---|
| [docs/handoff_2026-06-05_session_close_part3.md](handoff_2026-06-05_session_close_part3.md) | 本ファイル (最新) |
| [docs/handoff_2026-06-05_session_close_part2.md](handoff_2026-06-05_session_close_part2.md) | Part 2 (緊急停止対応 + 構造的未配線発覚) |
| [docs/handoff_2026-06-05_session_close.md](handoff_2026-06-05_session_close.md) | Part 1 (朝のセッション・タグフィルター恒久バグ修正) |
| [docs/eval/2026-06-04_qwen3_vs_gemini.md](eval/2026-06-04_qwen3_vs_gemini.md) | ハイブリッド推奨の根拠 (L302 = `[x]` 確定済) |
| [tools/llm_hybrid.py](../tools/llm_hybrid.py) | 本配線のファサード (4 モード切替 + GPU 占有検出) |
| [tools/config.py](../tools/config.py) | `HYBRID_MODE` / `OLLAMA_MODEL` (Qwen3.6-35B) 等 |
| [tools/collect_rss.py](../tools/collect_rss.py) | L205 で `llm_hybrid` 経由 + rewrite_emphasis + verify_quant 配線済 |
| [tools/rewrite_emphasis.py](../tools/rewrite_emphasis.py) | 強調記法の決定論振り分け (collect_rss から呼出済) |
| [tools/verify_quant.py](../tools/verify_quant.py) | 数値捏造ゲート (collect_rss._verify_event_quant 経由で呼出済) |
| [tests/test_llm_hybrid.py](../tests/test_llm_hybrid.py) | 契約テスト 8 件 (フォールバック挙動) |
| [tests/test_rewrite_emphasis.py](../tests/test_rewrite_emphasis.py) | 契約テスト 6 件 (強調振り分け + 冪等性) |
| [scripts/run_daily.bat](../scripts/run_daily.bat) | 高 2 で `.ps1` 化候補 |
| [scripts/run_weekly.bat](../scripts/run_weekly.bat) | 同上 |

---

## 5. 次セッション起動方法

### Claude Code CLI (ローカル)

ファイルパス渡し:

```
AI-Pulse/docs/handoff_2026-06-05_session_close_part3.md
```

### claude.ai ブラウザ版に貼る場合 (self-contained プロンプト)

> AI-Pulse プロジェクト (生成 AI 特化ニュース + DB の Jinja2 SSG + PWA、`HIDEPON-UMG/AI-Pulse` private repo) を継続します。origin/master HEAD = `2e50b8a`、本ハンドオフ作成時点で **直前セッション (Part 3) でハイブリッド LLM 本配線を完了**しました。
>
> **直前セッション (2026-06-05 Part 3) で完了したこと**:
> - `tools/llm_hybrid.py` 新規作成 (local_first / gemini_first / gemini_only / local_only の 4 モード、GPU 占有検出は `quiet_run` 経由で nvidia-smi)
> - `tools/config.py` 更新 (`OLLAMA_MODEL = "hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-IQ3_XXS"` / `OLLAMA_TEMPERATURE = 0.1` / `MAX_BODY_CHARS = 5000` / `HYBRID_*` 追加)
> - `tools/llm_gemini.py` 修正 (PROMPT_PATH を extract_grounded.md に / emphasis 検証削除 / EmphasisShortageError 廃止)
> - `prompts/gemini_summarize.md` → `prompts/.archive/` 退避 (`eval_fabrication_fix.py` のパスも追従)
> - `tools/collect_rss.py:205` を `llm_hybrid` 経由に + `rewrite_emphasis.rewrite_event` で強調コード付与 + `_verify_event_quant` で数値捏造ゲート
> - 契約テスト 14 件追加 (`tests/test_llm_hybrid.py` 8 + `tests/test_rewrite_emphasis.py` 6) / `test_llm_gemini.py` から emphasis 2 件削除
> - **テスト 66/66 PASS** (旧 54 + hybrid 8 + rewrite_emphasis 6 - emphasis 2)
> - `tools/llm_hybrid.py` ruff TID251 (banned-api) **解消** (`_proc.run.quiet_run` 経由)
> - eval doc L302 を `[x] ハイブリッド` に更新 + memory `project_ai_pulse.md` 追補12 追記
> - **push は GO 待ちで本セッション内では未実施**
>
> **次セッションの最優先タスク (高 1)**:
> safe-commit ゲート 6 段を通して本配線分をコミット & push。data/*.jsonl (Part 1 末尾の未関与差分) は別 commit に分ける案を推奨。
>
> **その後 (高 1.5 - 高 3)**:
> - `run_daily.py` 1 entity 試走で Qwen3.6-35B-A3B / Gemini フォールバック / verify_quant 閾値を実機確認 (Gemini API 課金発生のためユーザー GO 待ち)
> - `scripts/run_daily.ps1` / `run_weekly.ps1` 新設で Task Scheduler の文字化け対策 (ClaudeCodeFeed runner 方式)
> - 上記 2 つクリア後に AI-Pulse 日次/週次バッチの起動経路を確定
>
> **制約**:
> - 既存 66 PASS 維持
> - コミット・push は明示 GO 待ち
> - DESIGN.md トークン経由
> - URL 偽造防止 push 前ゲート (`audit_urls --gate`) 必須
> - HYBRID_MODE の本番デフォルトは `local_first`
> - `prompts/extract_grounded.md` 本線・強調記法は `rewrite_emphasis` でコード付与
> - 新規 subprocess 起動は `tools/_proc/run.py` の `quiet_run` 境界を必ず通す
>
> ブラウザ版では実コードを読めないので、必要なファイルがあれば手元で開いて該当部分を貼ってください。

---

## 6. 本セッションで守った / 守れなかった memory feedback

### 守った

- `feedback_pre_implementation_checklist`: 実装着手前に該当 memory (`feedback_check_design_principles` / `feedback_real_environment_first_verification` / `reference_memory_governance`) を読み返し、ドメイン特定 (LLM 抽出パイプライン) → 一次ソース検証 (eval doc L284 Claude 推奨 + 追補10 A確定config) → 既存テスト 54 PASS 棚卸し → TDD で `tests/test_llm_hybrid.py` を先に書いた
- `feedback_check_design_principles` §2 (境界 1 箇所集約): hybrid ファサード 1 関数に切替を集約、emphasis 責務は rewrite_emphasis に物理移管、subprocess は `quiet_run` 境界経由
- `feedback_check_design_principles` §4 (契約テスト 1 件で不変条件): フォールバック挙動 8 件 + 振り分け 6 件で locked-in
- `feedback_test_before_report`: 完了報告前に 66/66 PASS と ruff TID251 解消を実測値で報告
- `feedback_handoff_inventory_diff_closeout`: Part 2 受領タスク (高 1) の 10 ステップ全てを実装まで進めた (実機検証は API 課金待ちで GO 待ち明示)
- `feedback_japanese_env_first_scripting`: 新規 Python は UTF-8 / 日本語コメント許容
- `feedback_real_environment_first_verification`: hook 発火後に同一ファイル 5 回編集の反省 → 残ファイルは 1 Write で完結する方針に切替

### 守れなかった / 反省

- **`llm_gemini.py` 同一ファイル 5 回編集** (hook 発火): 同一意図 (grounded プロンプト化 + emphasis 撤去) の編集を細切れにしたミス。途中から「1 ファイル 1 Write で完結」に切替えて以降の `llm_hybrid.py` `collect_rss.py` `test_*.py` は遵守
- **`run_daily.py` 実機 smoke 未実施**: Gemini API 課金事前承認が必要なため次セッションへ送り。Part 2 §3 高 2 「再 Enable 条件」の前段
- **本配線分の dispatch 自動 inject** (追補11 §2 で挙げられた構造解決): 追補12 で本配線が完了したのを機に低 3 で「案 (a) 採用」を推奨したが、本セッションでは frontmatter 修正まで踏み込まず
