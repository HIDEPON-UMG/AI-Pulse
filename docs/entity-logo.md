# entity.logo 運用メモ

AI-Pulse は `data/entities.jsonl` の各 entity に、サービスロゴまたはアイコンの取得情報を `logo` として保持できる。

## フィールド

`entity.logo` は任意項目であり、存在する場合は `tools/schema.py` が形を検証する。

```json
{
  "logo": {
    "path": "assets/service-icons/<entity_id>.png",
    "source_url": "https://example.com/logo.png",
    "source_page": "https://example.com/brand",
    "fetched_at": "YYYY-MM-DD",
    "license_note": "official site asset, redistribution not verified",
    "status": "verified"
  }
}
```

`status` は `verified`、`candidate`、`missing` のいずれかである。公式 favicon や apple-touch-icon しか取れない場合は `candidate` を使う。公式ロゴの再配布ライセンスが明確でない場合は、`license_note` に `official site asset, redistribution not verified` のような控えめな記録を残す。

## 保存先

画像ファイルは repo 直下の `assets/service-icons/<entity_id>.png` に保存する。`tools/generate_pages.py` は `assets/` 配下の PNG を `site/assets/service-icons/` にコピーするため、カルテ HTML は `entity.logo.path` をそのまま相対パスとして参照できる。

AI-Pulse カルテ PPT 生成 skill は、`--logo` 指定を最優先し、次に `entity.logo.path`、次に `assets/service-icons/<entity_id>.png`、最後にプレースホルダーを使う想定でこのフィールドを読む。

## 更新方法

PC の PowerShell で AI-Pulse リポジトリに移動し、最初に候補だけを確認する。

```powershell
.\.venv\Scripts\python.exe tools\backfill_entity_logos.py --dry-run --limit 5
```

候補 URL が公式ページ由来であることを確認した後、対象 entity を指定して保存する。

```powershell
.\.venv\Scripts\python.exe tools\backfill_entity_logos.py --entity claude-opus
```

全件を更新する場合も、先に `--dry-run --limit 5` を実行して候補の傾向を確認する。スクリプトは取得元 URL、画像 MIME type、元画像サイズ、保存先、`status` を標準出力に記録する。取得に失敗した entity は `status: "missing"` として記録し、処理全体は継続する。

画像検索で拾った第三者サイトのロゴは使わない。スクリプトは既存 entity の公式履歴 URL と、その公式ドメインの favicon / apple-touch-icon / og:image / brand 系ページから候補を探す。
