# Scrapling fetch escalation

AI-Pulse の日次収集は Google News RSS を候補発見レイヤーとして維持し、publisher URL の
本文 HTML 取得が空応答・blocked になった場合だけ Scrapling に昇格する。

- 昇格順: `urllib` -> Scrapling `Fetcher` -> Scrapling `StealthyFetcher`
- 本文抽出: 引き続き `trafilatura.extract()` を使う
- 短文本文: `config.MIN_BODY_CHARS` 未満は採用しない
- 監査: `collect_rss.collect_entities()` の戻り値に `fetch_stage_counts` を出す
- 制御: `AI_PULSE_STEALTHY_BUDGET` で 1 実行あたりの `StealthyFetcher` 上限を変える

`StealthyFetcher` はヘッドレスブラウザを使うため、初回セットアップ時に venv 内で次を 1 回実行する。

```powershell
.\.venv\Scripts\scrapling.exe install
```
