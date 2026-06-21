# AI-Pulse プロジェクト固有指示

グローバル `CLAUDE.md` と `ProjectFolders/CLAUDE.md` の階層継承下で動く。重複は書かない。

## ChatGPT consult repo-local 設定

ChatGPT consult の共通運用は ProjectFolders の `AGENTS.md` / `CLAUDE.md` と global skill `tool-repo-harness-chatgpt-bridge` に従う。この repo には採用設定として `.codex/config.toml` と `.oracle/config.json` だけを置き、汎用 skill や Oracle wrapper を repo-local 正本として持たない。

## URL 偽造防止 (push 前必須ゲート)

LLM (Claude セッション) は URL を記憶ベースで捏造する既知バグがある (News-Grasp 2026-06-03 三菱UFJ FX_Monthly 事故で 803 件中 33 件 = 約 4% が 404/410 と判明)。AI-Pulse でも `entity.history[].url` / `entity.modules.future[].url` / `event.source_url` に同じ経路で捏造混入し得る。境界 1 箇所集約 + 契約テスト + push gate の三段で構造的に弾く ([[feedback_llm_url_fabrication_ban]] と [[feedback_check_design_principles]] §2/§4)。

### 構成

- **境界モジュール** [tools/validate_urls.py](tools/validate_urls.py): 3 段プローブ (HEAD ChromeWin → GET ChromeWin range → GET SafariMac range) で 404/410 即 FATAL、anti-bot 全段継続は ambiguous OK、DNS 解決失敗は捏造ホスト疑いで FATAL。`UrlFabricationError` を raise する `require_live_urls()` を持つ。
- **監査・ゲート CLI** [tools/audit_urls.py](tools/audit_urls.py): `entities.jsonl` + `events.jsonl` の全 URL を `validate_urls` で一括検証。`--gate` (= --recent 14 + 厳格 exit) / `--recent N` / `--max-workers N` をサポート。exit 0=健全 / exit 1=fatal 1 件以上。
- **契約テスト** [tests/test_urls_live.py](tests/test_urls_live.py): `audit_urls --gate` を subprocess で呼ぶ二重ガード。`AI_PULSE_SKIP_URL_CHECK=1` でスキップ可 (CI/オフライン用)。

### push 前必須手順

新規 entity / event を追加した、または `history[].url` / `source_url` を編集したコミットを push する前は、必ず以下を通す:

```powershell
# AI-Pulse プロジェクトルートで
./.venv/Scripts/python.exe tools/audit_urls.py --gate
```

exit 0 (= 直近 14 日の URL がすべて生存) を確認してから `git push`。1 件でも NG が出たら push せず、該当 URL を `WebSearch` / `WebFetch` で実機 200 確認できる URL に差し替えるか、URL ごと削除する (出典名のみ残す)。

新規 URL を `entities.jsonl` / `events.jsonl` に書くときの絶対ルール ([[feedback_llm_url_fabrication_ban]]):

- `WebSearch` の検索結果 / `WebFetch` で実アクセスして 200 (または 3xx) を確認できた URL **のみ** 書く
- 「ありそうな URL」「過去に見た記憶」「タイトルから生成したスラグ」「ホスト構造からの推測」は**例外なく禁止**
- 確認できないなら `source` フィールドに名前だけ残し `url` は省く

### 横展開した元プロジェクト

News-Grasp の [tools/validate_deepdive_urls.py](../News-Grasp/tools/validate_deepdive_urls.py) と [tools/audit_all_article_urls.py](../News-Grasp/tools/audit_all_article_urls.py) を AI-Pulse の jsonl 構造に合わせて移植したもの (md ブロック抽出は AI-Pulse では不要なので削除、抽出対象を `entity.history[].url` / `entity.modules.future[].url` / `event.source_url` の 3 経路に絞っている)。
