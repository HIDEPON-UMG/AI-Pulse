# Product Spec: AI-Pulse

> **Status**: Constitution
> **Last Updated**: 2026-06-22
> **Owner**: Planner

## Product Constitution

AI-Pulse は、生成AI領域の重要な動きを「ニュース断片」ではなく、プロダクト・企業・モデル・制度のカルテとして継続的に読める状態へ整理する。対象ユーザーは、生成AIの技術・事業・政策変化を追う実務者、企画者、調査担当者、投資・事業開発の意思決定者である。

このプロダクトの中心価値は、毎日のニュース収集、エンティティ別カルテ、イベント履歴、比較軸、公開サイト、運用ログをつなぎ、短時間で「何が起きたか」「なぜ重要か」「どのプレイヤーに効くか」を判断できることにある。単なる RSS 集約や話題一覧ではなく、継続的に更新される生成AI産業の地図を作る。

## Current Reality Snapshot

この spec は 2026-06-22 時点の実データを前提にする。

| Item | Current state | Spec implication |
|---|---|---|
| Entities | 32 entities | カルテはデモ段階を超え、カテゴリ横断の継続運用対象として扱う。 |
| Events | 440 events | 主課題は「初期記事不足」ではなく、継続収集、品質維持、公開鮮度、entity 間の偏り補正である。 |
| Categories | model 7 / editor 5 / media 5 / physical 4 / agent 6 / infra 3 / policy 2 | 新規機能は 7 lens のどれに効くか、または lens 横断かを明示する。 |
| Event gaps | `wai-series` has 0 linked events | カルテは存在するが event coverage が薄い entity を、収集・手動補完・除外判断の対象として扱う。 |
| Localization | `headline_ja` exists for 415 / 440 events | 全 event 完了済みとは扱わず、欠落分は品質改善 backlog とする。 |
| Visual assets | `thumb` exists for 426 / 440 events | UI 表示の欠落 fallback と補完方針を維持する。 |

## Core / Why / What / How

| Layer | Definition |
|---|---|
| Core | 生成AIの変化を、実務判断に耐える継続的な知識ベースとして届ける。日次運用、カルテ、公開サイト、品質監査が一体で回る状態を作る。 |
| Why | 生成AI領域はモデル、開発ツール、物理AI、メディア生成、エージェント、インフラ、政策が同時に動き、単発記事だけでは変化の意味を追いにくい。実務者は短時間で重要度、影響、プレイヤー間の関係を把握したい。既に 440 events あるため、単純増量より、偏り、鮮度、根拠、継続運用の品質が重要である。 |
| What | `data/entities.jsonl` の 32 entity カルテ、`data/events.jsonl` の 440 event、日次/週次バッチ、品質監査、GitHub Pages 公開サイト、BuzzPost / Repo Radar などの周辺ビューを提供する。 |
| How | RSS / Google News / 補助 LLM / ローカル LLM / URL 検証 / schema / quality audit / static site generation / publish script / scheduled task を、失敗時に追跡可能なログとテストでつなぐ。ChatGPT consult は要件レビュー補助であり、repo-local tests と公開確認を置き換えない。 |

## Definition of Done

- 日次バッチが、対象エンティティに関連するイベントを収集、重複排除、品質検査、保存、サイト再生成まで完了する。
- 公開サイトで、feed / archive / karte / BuzzPost / Repo Radar などの主要ビューが壊れず、ユーザーが最新の生成AI動向を確認できる。
- 新規 event は summary、summary_points、importance、impact、buzz、event_type、source_url などの必須品質条件を満たす。`headline_ja` と `thumb` は既存欠落があるため、新規追加時は原則付与し、既存欠落は backlog として補完する。
- 新規 entity / event の URL は推測で作らず、`tools/audit_urls.py --gate` または同等の検証で生存確認できる。
- 変更した機能に対応するテスト、品質 gate、公開確認、runner / publish state のいずれを更新したかが説明できる。

## Success Metrics

| Metric | Target / Use | Measurement |
|---|---|---|
| Freshness | 日次バッチ実行後、公開サイトが当日または直近実行分へ更新される | `_logs/daily_YYYYMMDD.log`、`tools/check_public_freshness.py`、公開 URL sentinel |
| Event coverage | 主要カルテに継続的な event が紐づく | `data/events.jsonl` の件数、entity ごとの recent_events、archive 件数 |
| Quality pass rate | schema / editorial lint / quality audit / URL gate がコミット前に通る | `pytest`、`tools/audit_urls.py --gate`、`tools/run_daily.py` 経由の `tools/quality_audit.py` |
| Public usability | feed / archive / karte が desktop / mobile で読める | site build、ブラウザ smoke、主要 UI 契約テスト |
| Operational recoverability | バッチ失敗時に原因、再実行ポイント、公開未反映が追える | `_logs/`、publish log、exit code、incident / handoff docs |
| Coverage balance | event が存在しない entity と極端な偏りを継続的に減らす | entity ごとの event 数、`wai-series` など 0 件 entity の有無 |

## Non-Goals

- 汎用ニュースサイトや全分野 RSS リーダーにはしない。
- 裏取りできない URL、日付、数値、出典を「ありそう」で掲載しない。
- ChatGPT / LLM のレビュー結果だけで、実装完了、品質合格、公開反映を判断しない。
- すべての生成AIニュースを網羅することを目的にしない。カルテとイベントの関係が追える範囲を優先する。
- 本人セッション、課金 API、外部ログインが必要な処理をユーザー承認なしに定期実行へ組み込まない。
- `site/` の公開経路が未解明な状態で、公開反映を `git push` 成功だけで完了扱いしない。

## Feature / Test Traceability Matrix

| Feature | Expected outcome | Verification command |
|---|---|---|
| Daily pipeline | RSS / related updates / site regeneration / publish handoff が途中失敗を隠さない | `PYTHONUTF8=1 python -m pytest tests/test_run_daily.py tests/test_run_daily_quality_audit.py tests/test_batch_failure_exit.py -q --tb=short` |
| Event quality | event extras、rationale、headline_ja、editorial lint が品質基準を満たす | `PYTHONUTF8=1 python -m pytest tests/test_schema.py tests/test_quality_audit.py tests/test_editorial_lint.py tests/test_collect_rss_editorial_lint.py -q --tb=short` |
| URL fabrication prevention | entity / event URL が推測混入せず、直近 URL gate を通る | `PYTHONUTF8=1 python tools/audit_urls.py --gate` |
| Site generation | feed / archive / karte / assets が生成でき、主要 UI 契約を満たす | `PYTHONUTF8=1 python -m pytest tests/test_generate.py tests/test_branding.py tests/test_entity_logos.py -q --tb=short` |
| Publish flow | commit/push 対象と freshness/public state を確認できる | `PYTHONUTF8=1 python -m pytest tests/test_publish_daily.py tests/test_check_public_freshness.py -q --tb=short` |
| BuzzPost / Repo Radar | 周辺ビューが AI-Pulse の目的から外れず収集・表示できる | `PYTHONUTF8=1 python -m pytest tests/test_collect_buzz_posts.py tests/test_collect_repo_radar.py tests/test_repo_radar_obsidian.py -q --tb=short` |
| Product spec governance | spec が実データ、既知 gap、検証コマンド、ChatGPT 境界を反映する | `PYTHONUTF8=1 python -m pytest tests/test_product_spec_contract.py -q --tb=short` |

## Acceptance Scenarios

| Scenario | Given | When | Then |
|---|---|---|---|
| Normal daily run | RSS と関連ソースが取得可能で、既知 entity に関連する新規 event 候補がある | 日次バッチを実行する | schema / quality / URL / 重複 gate を通った event だけが保存され、サイトが再生成される。 |
| Low quality candidate | LLM 出力が短すぎる rationale、曖昧な importance、または不正 URL を含む | collect / quality audit が実行される | 該当 event は採用されないか、明示的な修復・再実行対象になる。 |
| Public publish | データまたはサイト生成ロジックが更新される | publish script または手動 push を行う | remote HEAD、公開 freshness、主要ページの反映確認まで完了する。 |
| Planning new feature | 新しい収集ビュー、UI、バッチ、分類・スコアリングを追加する | 実装前 plan を作る | `docs/spec.md` の Core/Why/What/How と Feature/Test Traceability に接続し、不足があれば質問へ戻る。 |
| Coverage correction | entity に event がない、またはカテゴリ間で coverage が偏っている | 収集条件や手動補完を検討する | 追加対象、採用基準、検証コマンドを spec / issue / plan のいずれかに残してから実装する。 |
| ChatGPT consult | 非自明な要件変更で ChatGPT review consult を使う | reviewer 指摘を受ける | 指摘は採否判断の補助に留め、repo-local tests、URL gate、公開確認で最終判断する。 |

## Open Questions

- None.
