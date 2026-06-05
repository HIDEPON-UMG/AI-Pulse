# Handoff 2026-06-05 session close — Part 9 (Task Scheduler 構造解決 + hook 修正)

Part 8 完了後、handoff の P0「2026-06-06 朝 7:00 Task Scheduler 起動の観察」着手のため Task Scheduler の状態を確認したところ、**直近 3 日間 (06-03 / 06-04 / 06-05) すべての日次バッチが LastTaskResult=0 で「正常終了」しているにも関わらず `_logs/` にログが 0 件生成されていない構造バグ**が判明し、その真因の特定 → 恒久対策 → 実機検証まで実施したセッション。コンテンツ (entities / events) には一切触らず、運用基盤の修正のみ。

## 経緯と原因切り分け

### 1. 観測された矛盾事象

```
Task Scheduler "AI-Pulse 日次バッチ":
  Trigger: 毎日 7:00 (StartBoundary 2026-06-03T07:00:00)
  Action:  cmd /c "<...>\scripts\run_daily.bat"
  LastRunTime:    2026/06/05 7:00:01
  LastTaskResult: 0  (= 成功)
  _logs/ に .log: 0 件
```

`run_daily.bat` を Read してみると `>> "%LOG%" 2>&1` で `_logs/daily_<YYYYMMDD>.log` に書く設計だが、3 日分一つも残っていない。`%DATE%` 形式と書込み権限を確認したところ単体テストは生成成功 (`probe_redirect.log`)。

### 2. 真因 (.bat 側)

`.bat` 3 本 (`run_daily.bat` / `run_weekly.bat` / probe) を `[System.IO.File]::ReadAllBytes` で確認したところ全て **LF only / BOM 無し / UTF-8** で保存されていた。Task Scheduler の cmd は CRLF を期待し、CP932 で読むため:
- 日本語 rem コメント → `rem` 認識されず無効コマンド扱い
- `%DATE:~0,4%` → 展開されず文字列扱い
- 結果として全行エラーになるが cmd 自体は exit 0 で完了 → LastTaskResult=0

Task Scheduler エミュレートで実機実行したところ exit 255 + stderr に `'��ロ:' is not recognized`, `'E:~0' is not recognized` 等の典型症状を確認。

### 3. 真因 (hook 側 — 構造的問題)

`.bat` が UTF-8 / LF only のまま残った理由は、CLAUDE.md グローバルが言う `enforce_script_encoding.ps1` PostToolUse hook が **Write 直後にも CRLF + CP932 変換していなかったため**。これは hook の登録ミスではなく、**hook の中で pwsh wrapper → Python に渡る stdin payload で日本語パスが文字化けし、`os.path.isfile()` が必ず False を返して FAIL-OPEN で無音 exit 0 する構造バグ**だった。

切り分け手順:

1. wrapper に DEBUG TRACE を仕込んで `$env:LOCALAPPDATA\claude-hook-trace\` に stdin dump → wrapper は起動している (= hook 登録は正しい) ことを確認
2. stdin dump を Read → `tool_input.file_path` が `c:\\Users\\hidek\\OneDrive\\繝峨く繝･繝｡繝ｳ繝・\\ProjectFolders\\...` と化けていた
3. pwsh の `[Console]::InputEncoding` がデフォルト CP932 だが、Claude Code は UTF-8 で stdin に payload を送るため不整合

4. wrapper の stdin 読みを `StreamReader([Console]::OpenStandardInput(), [Text.UTF8Encoding]::new($false))` に修正 → stdin dump の日本語が「`ドキュメント`」と正常に読めるようになった
5. しかし依然 `python_exit=0` で変換されない → wrapper → Python の native pipe で再エンコード問題
6. wrapper 側で `$OutputEncoding = New-Object System.Text.UTF8Encoding($false)` 設定 → それでもダメ (Python 側 sys.stdin が cp932 で読む)
7. Python 側で `sys.stdin.reconfigure(encoding="utf-8", errors="replace")` を main 冒頭で実行 → ようやく hook が CRLF + CP932 変換するようになった

この 2 段の真因 (wrapper の InputEncoding + Python の sys.stdin encoding) は、日本語パス配下のファイルを編集する全 Python hook に共通する潜在バグ。詳細は memory [reference_hook_stdin_utf8_payload](https://github.com/ — local memory file) に永続化済み。

## 適用した修正

### 1. Task Scheduler Action を `.bat` から `.ps1` に切替え (構造解決)

`Set-ScheduledTask` で `AI-Pulse 日次バッチ` と `AI-Pulse 週次バッチ` の両方を更新:

```
Execute   : powershell.exe
Arguments : -NoProfile -ExecutionPolicy Bypass -File "C:\Users\hidek\OneDrive\ドキュメント\ProjectFolders\AI-Pulse\scripts\run_daily.ps1"
                                                                                                                                  ↑ 週次は run_weekly.ps1
```

`.ps1` は UTF-8 BOM 付き設計で encoding 問題を構造的に消すため、cmd の CP932/CRLF 問題が再発しない。

### 2. `~/.claude/hooks/enforce_script_encoding.{ps1,py}` を恒久修正

wrapper (`enforce_script_encoding.ps1`):
- `$OutputEncoding = New-Object System.Text.UTF8Encoding($false)` を冒頭に追加
- stdin 読みを `StreamReader([Console]::OpenStandardInput(), [Text.UTF8Encoding]::new($false))` に変更

本体 (`enforce_script_encoding.py`):
- `main()` 冒頭の `sys.stderr.reconfigure(...)` の直後に `sys.stdin.reconfigure(encoding="utf-8", errors="replace")` を追加

修正後 probe (`_probe_after_fix3.bat`) を Write したところ、hook が正しく `UTF-8 → CP932 + CRLF` 変換を実行し stderr に通知 → 実機で動作確認完了。

### 3. 古い `.bat` の削除と probe 整理

- `AI-Pulse/scripts/run_daily.bat` 削除 (Task Scheduler は `.ps1` を参照)
- `AI-Pulse/scripts/run_weekly.bat` 削除 (同上)
- 切り分け用 probe `.bat` / `.ps1` 全削除
- `$env:LOCALAPPDATA\claude-hook-trace\` 削除 (DEBUG TRACE 跡片付け)
- wrapper の DEBUG TRACE 削除 (Write で wrapper 全文を清書)

## 実機検証

Task Scheduler 起動と同じ条件 (`Set-Location 'C:\Windows\System32'` + `powershell.exe -NoProfile -ExecutionPolicy Bypass -File <ps1>`) で probe を実行した結果:

```
exit code: 0
_logs/probe_ps1_20260605.log (484 bytes) 生成:
  [2026-06-05 18:20:47] probe_ps1_path 開始 (Python skip)
  AiPulse=C:\Users\hidek\OneDrive\ドキュメント\ProjectFolders\AI-Pulse
  LogsDir=C:\Users\hidek\OneDrive\ドキュメント\ProjectFolders\AI-Pulse\_logs
  LogPath=C:\Users\hidek\OneDrive\ドキュメント\ProjectFolders\AI-Pulse\_logs\probe_ps1_20260605.log
  Cwd=C:\Windows\System32
  PSScriptRoot=C:\Users\hidek\OneDrive\ドキュメント\ProjectFolders\AI-Pulse\scripts
  [2026-06-05 18:20:47] probe_ps1_path 終了
```

- 日本語が文字化けせず UTF-8 で記録
- Cwd=System32 (= Task Scheduler 起動時の cwd を再現)
- `$PSScriptRoot` が `.ps1` の置かれているパスに正しく解決

→ 明日 (2026-06-06) 朝 7:00 ジョブで `_logs/daily_20260606.log` が UTF-8 で確実に生成される状態に到達。

## 残タスク

### P0 (繰越し)

**2026-06-06 朝 7:00 Task Scheduler 起動の観察** — Part 8 から繰越し。今回の修正で前提条件 (.ps1 が回ってログが書ける) は整ったので、次セッションで:

1. `_logs/daily_20260606.log` が UTF-8 文字化けなしで生成されているか
2. 新規採用 entry (events.jsonl 追記分) に headline_ja が自動付与されるか
3. 新規採用 entry の rationale 3 軸 (importance / impact / buzz) が 20 字以上を満たすか (Part 7 schema 強化が collect_rss でも有効か実機確認)
4. 満たさない場合 `llm_local._call_once` の schema retry で救えるか

### P1 — Part 6/7 残 (Part 8 から繰越し・ユーザー指示時のみ)

1. LLM 意味反転誤訳の全件監査
2. rationale の字数上限 (maxLength) 追加検討
3. collect_rss の entity_context 渡し方統一

### P2 — Part 8 新規 (繰越し)

1. `reference_civarchive_secondary_source.md` の memory 作成 (内容案握り済み)
2. WAI シリーズ追加派生の追跡 (発生時のみ)
3. anima-base ↔ wai-series 双方向リンク (任意)

### P3 — Part 9 新規 (今回の修正の横展開)

- **他 Python hook への同型修正の横展開検討**: `validate_memory_write` / `enforce_runner_smoke` / `validate_digest_ja_callout` / `flag_ui_edit` / `warn_repeated_edit_same_file` 等の PostToolUse hook も同じ二段 encoding 問題を抱える可能性。日本語パス配下のファイルを Write/Edit したとき hook の挙動を確認し、必要に応じて wrapper + Python 両方に同じ修正を入れる。

### P3 (継続オープン項目)

AI-Pulse のメイン主題「**記事増加**」(events 171 件 / entities 30 件 / physical 0 件 / パイプライン未ライブ運用) は Part 4 引継ぎ `docs/handoff_2026-06-03_articles_expansion.md` に集約済み。今回も周辺整備で本筋は未着手。

## コミット内容 (本 Part 9)

- `AI-Pulse/scripts/run_daily.bat` 削除
- `AI-Pulse/scripts/run_weekly.bat` 削除
- `AI-Pulse/docs/handoff_2026-06-05_session_close_part9.md` 新規 (本ファイル)

`~/.claude/hooks/enforce_script_encoding.{ps1,py}` と `~/.claude/projects/.../memory/reference_hook_stdin_utf8_payload.md` の修正は AI-Pulse リポジトリ外なので本 commit には含まれない。Claude Code 設定側の永続化として個別管理。

push 先: `HIDEPON-UMG/AI-Pulse` origin/master (ユーザー指示時のみ)
