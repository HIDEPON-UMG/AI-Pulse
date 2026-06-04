# ローカル LLM 抽出置換 調査レポート（2026-06-04）

> AI-Pulse の抽出処理（記事本文 → summary/summary_points/rationale/score/importance/event_type の構造化 JSON）を、
> Gemini API からローカル LLM（Ollama / RTX5080 16GB）へ置換できるかの調査。
> 関連生データ: [4-way 比較](2026-06-04_qwen3_vs_gemini.md) / [盲検ジャッジ](2026-06-04_blind_judge.md) / [生スコア JSON](2026-06-04_blind_judge_raw.json)

---

## 0. エグゼクティブサマリ

- **品質は 35B-A3B ≈ flash-lite の互角（強みの交換）**。qwen3:14b は明確に 3 番手。
- **盲検ジャッジ総合**: 35B-A3B **3.80** > flash-lite 3.38 > qwen3:14b 3.02（各 1-5）。ただし総合の逆転は **rationale 次元がほぼ単独で駆動**しており、**factual（事実忠実度）はむしろ flash-lite が上**。
- **ローカル化の動機は「品質向上」ではない**。コストは flash-lite で既に $0.015/76 件。動機は **APIクォータ非依存・オフライン自走・考察記事(essay)の同モデル一本化・環境活用**。品質は「維持」が正しい理解。
- **Claude 推奨**: 抽出は **35B-A3B 一本化**（essay と同モデル・判定品質最良・~22分/76 は夜間バッチで許容）、**qwen3:14b は見送り**、**ハイブリッド**（local 失敗/GPU 占有時に Gemini フォールバック）。
- **最大の watch-item**: ローカルは**固有名詞・数値の捏造がやや多い**（ニュース DB では致命的になりうる）。

| 観点 | flash-lite（Gemini基準） | qwen3:14b | 35B-A3B |
|---|---:|---:|---:|
| 盲検総合（1-5） | 3.38 | 3.02 | **3.80** |
| factual 忠実度 | **3.90** | 3.20 | 3.30 |
| rationale 深さ | 1.80 | 2.80 | **4.20** |
| 76件直列スループット | API | 約16分 | 約22分 |
| 完走率（強調無効条件） | 11/11 | 11/11 | 11/11 |
| クォータ/オフライン | 依存（Free Tier削減リスク） | 非依存 | 非依存 |

---

## 1. 背景と動機

AI-Pulse の LLM 呼び出しは **1 箇所に集約**されている（`tools/llm_gemini.py` の `generate_event_extras`）。用途は記事本文からの構造化 JSON 抽出のみ。考察記事(essay)生成は News-Grasp 由来の構想で AI-Pulse 未実装。

**コストは動機にならない**: 評価済みのとおり flash-lite で 76 件 ≈ **$0.015**。ローカル化しても金銭的節約はほぼゼロ（むしろ電気代・GPU 占有が増える）。したがって本調査の動機は以下:

| 動機 | ローカル化の効きどころ |
|---|---|
| API クォータ非依存 | Google が Free Tier を 50-80% 削減済み。RPD 1000 が将来の収集件数増で天井になる |
| オフライン自走 | API キー管理・外部 API 障害（先日の Claude 障害のような）から独立 |
| 考察記事(essay)の追加 | 長文生成は Gemini Free Tier の quota を食う。35B-A3B ならローカルで青天井 |
| 環境活用・実験 | RTX5080 + Ollama を実運用に乗せる |

**ローカルモデル対応（ユーザー設定の役割分担）**:
- 要約・抽出（指示遵守重視）→ **qwen3:14b**（9.3GB / dense 14B）
- 考察記事（長文・高品質）→ **Qwen3.6-35B-A3B**（14GB / MoE 35B-A3B / IQ3_XXS）

---

## 2. 調査の流れ（4 段階）

| 段階 | 内容 | 主要な発見 |
|---|---|---|
| ① 実機プローブ | qwen3:14b に `think:false` + schema 拘束で 1 投 | think:false でクリーン JSON・`format` でスキーマ遵守を確認（最大リスク解消） |
| ② 2-way eval | flash-lite vs qwen3:14b（5サンプル） | qwen3 は概ね通るが maxLength 語中切れ・強調記法の誤実行を観測 |
| ③ 4-way eval | flash/flash-lite/qwen3/35B（5サンプル） | qwen3 が強調契約で 2/4 脱落・35B は 4/4 堅牢だが ~44s/件。maxLength は両ローカル共通の地雷 |
| ④ 盲検ジャッジ | N=12、強調無効+maxLength緩和、gemini-flash 盲検採点 | 下記 §3。条件を計画アーキに合わせた公平比較 |

**設計上の朗報**: LLM 境界が 1 箇所のため、`llm_local.py`（同契約のローカルバックエンド）を新設し config スイッチで切替えるだけ。**可逆・低リスク**。`tools/llm_local.py` はプロンプト・スキーマ・shape 検証を `llm_gemini` から再利用している。

---

## 3. 定量結果（盲検ジャッジ・最も厳密な比較）

### 方法
- **N=11**（本文取得成功）/ **採点 10 件**（3 モデル全成功サンプルのみ。1 件は Gemini ジャッジが 503 で欠測）。
- **評価条件（計画アーキを先取りして公平化）**: 強調契約を無効化（強調はコード付与へ移す決定済）+ maxLength を 400 に緩和（語中切れ confound 除去）。3 モデル同条件・同プロンプト・temp 0.4。
- **盲検**: 各サンプルで 3 出力を候補 A/B/C に index ローテーションで shuffle（モデル名隠蔽・位置バイアス回避）。`gemini-2.5-flash` が本文を見て rubric 採点。**マークアップは評価対象外**と明示。
- **バイアス注記**: ジャッジが Gemini 系のため flash-lite 有利の系統誤差リスクあり → rubric を客観軸（事実=本文照合 / 完全性=切れ / rationale=ラベル反復減点）に寄せて緩和。**結果はその予想に反し 35B が flash-lite を上回った**ため、35B 評価はバイアスを差し引いても堅い。

### スコア集計（各軸 1-5・5 が最良）

| モデル | factual | summary | points | rationale | 総合 | Δ総合 |
|---|---:|---:|---:|---:|---:|---:|
| flash-lite | **3.90** | 3.90 | **3.90** | 1.80 | 3.38 | 基準 |
| qwen3:14b | 3.20 | 3.30 | 2.80 | 2.80 | 3.02 | −0.35 |
| 35B-A3B | 3.30 | **4.00** | 3.70 | **4.20** | **3.80** | **+0.42** |

### スループット（強調無効・warm 状態）

| モデル | 1件平均 | 76件直列推定 |
|---|---:|---:|
| qwen3:14b | 12.5s | 約16分 |
| 35B-A3B | 17.2s | 約22分 |

※ 4-way で 35B が 44s/件だったのは**強調契約のリトライで膨れていた**ため。強調を外すと ~17s/件に短縮。

---

## 4. 詳細エビデンス（ジャッジコメント根拠）

総合スコアの内訳を理解するため、ジャッジの個別コメント（[生 JSON](2026-06-04_blind_judge_raw.json)）から要点を引用する。

### 4-1. flash-lite の rationale が低い（1.80）= ラベル反復（捏造でなく正当）
ジャッジは 7/10 サンプルで flash-lite の rationale を減点。コメント例:
- claudeop-gem05: *"the rationale section is very weak, only providing 'mid' labels without any explanation"*
- flux-gem01: *"rationale の項目がラベルのみで、説明が一切ないため、評価基準に照らして大幅な減点"*
- physical-gem02: *"the rationale section merely repeats parts of the article without adding analytical depth"*

→ **flash-lite が importance/impact/buzz を `high`/`mid` のラベルだけで返すケースが多発**。これは本番でも起きている可能性のある**既存の品質課題**（§6 で要確認）。

### 4-2. 35B の rationale が突出（4.20）= 含意・波及・矛盾まで踏み込む
- cursor-gem03: *"論理的根拠も深く、含意や波及効果まで言及されている"*
- flux-gem01: *"importance、impact、buzz のそれぞれについて、論理的かつ深い考察がされており、非常に優れている"*
- （4-way の devin 記事）35B は「人間を代替しない」発言と「89% が AI コミット」の**矛盾を自ら指摘**。

→ **35B は指示遵守が強く rationale を一貫して深く書く**。flash-lite/qwen3 は importance 軸をラベルに退化させがち＝**プロンプトの rationale 指示が弱く小型モデルが落ちる**問題に 35B は頑健。

### 4-3. ローカルは factual 捏造がやや多い（watch-item）
- claudeop-gem03 / 35B: *"summary_points の4点目で「Rajesh Jha」という人物名と内部メモの内容が記事本文にない捏造であり、事実正確性が大きく損なわれている"*
- physical-gem01 / qwen3: *"「Prof. GUO Song」や「アジア太平洋地域」など、記事本文にない複数の事実誤認"*
- physical-gem01 / 35B: *"「郭松教授」と「アジア太平洋地域」という、記事本文にない情報"*

→ **ローカルは固有名詞・地域・数値を捏造する傾向が flash-lite より強い**（factual 3.2-3.3 vs 3.90）。ニュース DB では最重要のリスク。

### 4-4. qwen3 は markdown 自己言及をリーク
- claudeop-gem05 / qwen3: *"self-referential text about markdown/formatting ('下線 された', '==マーカー== された')... refers to elements not present in the source article"*

→ **強調検証を無効化してもプロンプトに強調指示が残るため qwen3 はリークし続ける**。強調コード化は**プロンプトからの強調指示除去**も必須。

### 4-5. 一部の捏造は本文 3000 字打切り由来（全モデル共通）
- devin-gem03: 全モデルが「89% のコードを Devin がコミット」を捏造（flash-lite factual=2 / qwen3=1 / 35B=2）。
- devin-gem05: 全モデルが過去調達ラウンドの金額・評価額を捏造（全モデル factual=1）。

→ これは**モデル差でなく `MAX_BODY_CHARS=3000` の打切りで本文が欠け、モデルが学習知識で穴埋め**した結果。**本文取得の改善で全モデル改善余地**がある。

---

## 5. 「強みの交換」の構図（最重要の解釈）

| 次元 | 勝者 | 差 |
|---|---|---|
| factual 忠実度 | **flash-lite** | local が固有名詞捏造で −0.6 |
| summary | 35B ≈ flash-lite | ほぼ同等 |
| points | flash-lite ≳ 35B | flash-lite やや上 |
| rationale 深さ | **35B** | flash-lite が +2.4 で大敗（ラベル化） |

**結論**: 総合では 35B が上だが、それは **35B が rationale で大きく勝ち、flash-lite が factual で勝つ**という交換。**コア抽出（factual/summary/points）は flash-lite ≳ 35B**。
→ **品質は実質互角**。ローカル化は「品質向上」でなく「品質維持 + 非機能要件（クォータ/offline/essay 一本化）」で評価すべき。

---

## 6. 未解決の論点 / 要確認

1. **【解決済】flash-lite の rationale ラベル化は実在**。本番 `events.jsonl` を確認したところ rationale はすべて full の理由文（例: 「主力 AI エディタの機能更新だが、基盤の作り替えではなく実行モードの追加に留まるため重要度を中と判定」）。ただし**本番は flash（gemini-2.5-flash）出力で確定済み**で、私が eval したのは **flash-lite**。つまり: **flash=rationale 充実 / flash-lite=不安定にラベル退化（N=10 で 7/10）/ 35B=一貫充実**。
   → **副次発見: 以前結論づけた flash→flash-lite のコスト切替は rationale 品質を劣化させるリスク**（4サンプルでは偶然 full だったが N=10 で露呈・temperature 0.4 のばらつきで不安定）。**35B なら flash 級の rationale をクォータ非依存で得られる**ため、この点は 35B 推奨を補強する。
2. **factual 捏造の本文打切り寄与**。`MAX_BODY_CHARS` 引上げ + 本文抽出改善で全モデルの factual が上がる可能性。ローカル採否と分離して検討。
3. **N=10・単一 Gemini 系ジャッジ**の限界。サンプルを増やす / 別系統ジャッジ（Claude 等）を足せば確度は上がるが、現状でも方向性（35B≈flash-lite・qwen3 劣後）は安定。

---

## 7. 最終モデル選定（決定マトリクス）

| 案 | 品質 | 速度 | 運用 | 非機能（クォータ/offline） | 備考 |
|---|---|---|---|---|---|
| **35B-A3B 一本化（推奨）** | flash-lite と互角（rationale 勝・factual 負） | ~22分/76（夜間OK） | **essay と同モデル・1モデル常駐で単純** | ◎ | watch-item=factual |
| qwen3:14b | 3 番手（factual/points 低・leak） | ~16分/76（最速） | essay と別モデル → ロード切替発生 | ◎ | 速度差6分は夜間で僅少 |
| flash-lite 維持 | 基準 | API | 現状維持 | ✗（依存継続） | 品質互角ならローカル化しない選択も合理 |

**推奨理由**: 品質互角・essay と同モデルで運用最単純・非機能要件を満たす。qwen3 は品質劣後かつ速度差が小さく、選ぶ理由が薄い。factual 忠実度はハイブリッド + 本文打切り緩和で手当て。

---

## 8. 確定後の実装前提作業（モデル選定とは独立に必要）

1. **プロンプトから強調指示を除去** + 強調は `tools/rewrite_emphasis.py` で**コード付与**（qwen3 リーク・flash-lite 脱落を同時解消）。
2. **maxLength を緩和**（280→~400）またはローカル用スキーマで撤廃（語中切れ防止）。
3. **collect_rss に config backend スイッチ + フォールバック配線**（local 失敗/GPU 占有時に Gemini）。
4. **`MAX_BODY_CHARS` 引上げ検討**（打切り由来の factual 捏造を全モデルで抑制）。
5. **契約テスト 1 件**: ローカルバックエンドが同契約 dict を返すことを locked-in（個別 smoke でなく境界 1 件）。

---

## 付録: 関連ファイル

- 新設: [`tools/llm_local.py`](../../tools/llm_local.py) — Ollama 版バックエンド（同契約）
- 新設: [`tools/eval_local_extraction.py`](../../tools/eval_local_extraction.py) — N-way 比較
- 新設: [`tools/eval_blind_judge.py`](../../tools/eval_blind_judge.py) — 盲検ジャッジ採点
- config 追記: [`tools/config.py`](../../tools/config.py) — `OLLAMA_*` 設定
- 既存境界: [`tools/llm_gemini.py`](../../tools/llm_gemini.py) / [`tools/schema.py`](../../tools/schema.py)
