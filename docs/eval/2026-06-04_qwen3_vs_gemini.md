# ローカル各モデル vs gemini flash/flash-lite 抽出品質比較（2026-06-04）

## 目的

抽出処理（generate_event_extras）をローカル LLM に置換できるか・どのローカルモデルが最良かを判断するため、eval_flash_vs_lite と同じ 5 サンプルの publisher 本文を再取得し、gemini-2.5-flash / gemini-2.5-flash-lite / qwen3:14b / Qwen3.6-35B-A3B (IQ3_XXS)（think=false・同一プロンプト・同一スキーマ拘束・temp 0.4）で side-by-side 比較する。

## サンプル選定

| event_id | category | event_type | headline |
|---|---|---|---|
| 2025-03-25-gemini25pro | model | release | Google、Gemini 2.5 Pro を公開 — 思考モデルでコーディング・数学ベンチトップ |
| 2026-06-03-claudeop-gem01 | model | benchmark | I compared Claude Opus 4.8 with 4.7 in a 10-round honesty te |
| 2026-06-02-claudeop-gem03 | model | regulation | Microsoft tells engineers to stop using Anthropic's Claude,  |
| 2026-06-02-claudeop-gem05 | model | incident | Claude AI Down for Users as Anthropic Confirms Outage |
| 2026-05-29-devin-gem03 | agent | release | Cognition’s Scott Wu says AI coding agents shouldn’t replace |


### 1. Google、Gemini 2.5 Pro を公開 — 思考モデルでコーディング・数学ベンチトップ

**本文再取得失敗**: `fetch_url 空応答: https://blog.google/technology/google-deepmind/gemini-2-5-pro-latest-thinking-model/`


### 2. I compared Claude Opus 4.8 with 4.7 in a 10-round honesty test

- **publisher**: https://www.zdnet.com/article/claude-opus-4-8-honesty-test/
- **category / event_type (ground truth)**: model / benchmark
- **本文文字数（再取得時点）**: 3000

#### flash 出力

- **score / importance / event_type**: 80 / high / benchmark
- **summary**: **Anthropic** の最新大規模言語モデル **Claude Opus 4.8** が、前バージョン **4.7** と比較して「正直さ」と「判断力」が向上したという主張を検証する **10ラウンドのテスト** が __実施__ されました。テストでは **Opus 4.8** が不確実性への対処で改善を見せたものの、特に法的プロンプトにおいて ==「とんでもない判断ミス」== が __発見__ され、法的確実性を捏造する問題が露呈しました。これにより、**Claude** の判断力を完全に信頼するにはまだ課題があることが __示唆__ されています。
- **summary_points**:
  - **Claude Opus 4.8** と **4.7** の正直さ・判断力を __比較__ する **10種類のテスト** を __実施__。
  - **Opus 4.8** は不確実性への対処で **4.7** より改善が見られた。
  - しかし、**Opus 4.8** で法的プロンプトにおいて ==「とんでもない判断ミス」== が __発見__ され、法的確実性を捏造。
  - **ChatGPT Codex** や **Gemini** などの複数の **AI** を用いてテスト結果を相互検証した。
  - **Anthropic** の **Claude** が完全に信頼されるには、判断力のさらなる向上が課題。
- **rationale**:
  - **importance**: **Claude Opus** の最新バージョンに関する客観的な性能評価であり、モデルの信頼性に関わる重要な情報です。
  - **impact**: **Claude Opus** の利用者や、LLMの信頼性を評価する研究者にとって、モデルの限界と改善点を示す具体的なデータとなります。
  - **buzz**: 主要なLLMの最新バージョンの性能比較は常に注目度が高く、特に「正直さ」や「判断ミス」といったテーマは関心を引きます。

#### flash-lite 出力

- **score / importance / event_type**: 75 / mid / benchmark
- **summary**: Anthropicの最新LLM **Claude Opus 4.8**は、先行モデル**4.7**と比較して不確実性への対応が向上しましたが、__法的文書の偽造__を試みるなど、依然として判断ミスが見られました。複数のAIによるクロスチェックでも、たとえ正直なAIでも誤った前提に基づいて不合理な判断をすることが示されました。
- **summary_points**:
  - **Claude Opus 4.8**は**4.7**より不確実性への対応が改善。
  - __法的文書の偽造__を試みる重大な判断ミスが**Opus 4.8**で確認された。
  - 複数のAIによるクロスチェックで、AIの判断能力が検証された。
  - 正直なAIでも、誤った前提から不合理な結論を導く可能性が示唆された。
- **rationale**:
  - **importance**: Claude Opus 4.8のリリースとその信頼性に関する検証は、AIの進化と実用化における重要な側面を照らし出す。
  - **impact**: 今回のテスト結果は、AnthropicのAIモデルの信頼性に対する評価に影響を与え、今後の開発の方向性を示唆する可能性がある。
  - **buzz**: Claude Opus 4.8の「正直さ」という特徴的な機能に対する検証は、AIコミュニティや一般ユーザーの関心を集めるトピックである。

#### qwen3:14b 出力

```
LLMError: Ollama 呼び出しが尽きました（2 回試行）: EmphasisShortageError: 太字 `**X**` だけで `==マーカー==` も `__下線__` も使われていません。記事に数値・結論・規模があれば `==マーカー==` を、発表・公開・採用・買収など動作があれば `__下線__` を最低 1 つ入れてください。
```

#### Qwen3.6-35B-A3B (IQ3_XXS) 出力（53.2s）

- **score / importance / event_type**: 65 / mid / benchmark
- **summary**: **ZDNET**は**Claude Opus 4.8**の「誠実さ」を10ラウンドのテストで検証した結果、__改善が確認__されたものの、重大な判断ミスも発見。複数のAIで結果を検証したが、==完全な信頼には至らない==ことが示唆され、実用化における課題が残る。
- **summary_points**:
  - **ZDNET**は**Claude Opus 4.8**の誠実性を10ラウンドのテストで検証し、__改善が確認__された一方で重大な判断ミスも発見
  - **OpenAI ChatGPT Codex**や**Gemini**などで結果を__クロスチェック__したが、==完全な信頼には至らない==実態が浮き彫りになった
  - テストはコードエッジケースから法的トラップまで多岐にわたり、**Claude Opus 4.7**との比較で__相対的な優位性__を検証
- **rationale**:
  - **buzz**: **ZDNET**が独自に実施したベンチマーク結果であり、AI業界の関心事であるモデルの信頼性に関する検証記事。
  - **impact**: **Claude Opus 4.8**の判断能力が前回比で改善したものの、重大な誤答が発覚し、完全な信頼には至らない実態を示す。
  - **importance**: 主要AIベンダー間の性能差や信頼性向上の実効性を評価する上で参考となる、具体的な事例分析であるため中程度と判定。


### 3. Microsoft tells engineers to stop using Anthropic's Claude, as canceling Claude 

- **publisher**: https://timesofindia.indiatimes.com/technology/tech-news/microsoft-tells-engineers-to-stop-using-anthropics-claude-as-canceling-claude-code-licenses-becomes-an-easy-way-to/articleshow/131456474.cms
- **category / event_type (ground truth)**: model / regulation
- **本文文字数（再取得時点）**: 3000

#### flash 出力

- **score / importance / event_type**: 80 / high / release
- **summary**: **Microsoft** は、社内エンジニアに対して **Anthropic** の **Claude Code** の利用を __停止__ し、自社の **GitHub Copilot CLI** への __移行を推進__ している。昨年12月に提供された **Claude Code** が予想以上に人気を博し、自社製品の利用を上回ったことが背景にある。公式にはツールチェーンの統一が理由とされているが、会計年度末の ==6月30日== を期限とするライセンスの __キャンセル__ は、AI利用にかかるコスト削減が主な動機であると **The Verge** は報じている。この動きは、AI導入に伴う費用が企業に与える影響を示すものだ。
- **summary_points**:
  - **Microsoft** は社内エンジニアに対し、**Anthropic** の **Claude Code** の利用を __停止__ するよう指示。
  - 昨年12月に提供された **Claude Code** は、**Microsoft** の **GitHub Copilot CLI** よりも人気を集めていた。
  - 公式理由はツールチェーン統一だが、==6月30日== のライセンス __キャンセル__ はコスト削減が主な動機と見られる。
  - **Microsoft** の **Experiences + Devicesチーム** が移行を主導し、**GitHub Copilot CLI** への集約を図る。
- **rationale**:
  - **importance**: **Microsoft** のような大手企業がAIツールの利用方針を転換することは、業界全体への影響が大きく、特に自社製品優先の姿勢は注目に値する。
  - **impact**: **Anthropic** の **Claude Code** の社内利用が制限されることで、**Microsoft** 社内の開発ワークフローに影響が出る。また、AIツールのコスト問題が顕在化した事例として、他社にも波及する可能性がある。
  - **buzz**: **Microsoft** と **Anthropic** という主要AI企業間の動向であり、**GitHub Copilot CLI** との競合も絡むため、業界内外で高い関心を集める。

#### flash-lite 出力

- **score / importance / event_type**: 75 / mid / release
- **summary**: **Microsoft** は、社内エンジニアによる **Anthropic** の **Claude Code** の利用を 6 月 30 日で終了し、自社製品 **GitHub Copilot CLI** への移行を指示しました。Claude Code が想定以上に社内で普及し、自社製品の利用を圧迫したため、公式にはツールチェーン統合が理由ですが、期末のコスト削減が背景にあると見られています。Claude モデル自体は Copilot CLI 経由で引き続き利用可能です。
- **summary_points**:
  - **Microsoft** は 6 月 30 日をもって、社内エンジニア向けの **Claude Code** ライセンスを __終了__ します。
  - 移行先として、自社製品である **GitHub Copilot CLI** の利用を __推奨__ しています。
  - Claude Code が社内で想定以上に __普及__ し、自社製品の利用を __圧迫__ したことが背景にあります。
  - 公式理由はツールチェーン統合ですが、期末の __コスト削減__ が主因と報じられています。
  - Claude モデル自体は Copilot CLI 経由で __引き続き利用可能__ です。
- **rationale**:
  - **importance**: Microsoft が自社開発 AI 製品を優先するため、競合ツールの社内利用を制限するという決定は、AI 開発競争における戦略的な動きとして重要です。
  - **impact**: エンジニアのツール選択に影響を与え、GitHub Copilot CLI の利用拡大を促す可能性があります。また、AI ツールのコスト管理の重要性を示す事例となります。
  - **buzz**: Microsoft による競合 AI ツールの社内利用制限というニュースは、AI 業界関係者や開発者の間で注目を集める可能性があります。

#### qwen3:14b 出力

```
LLMError: Ollama 呼び出しが尽きました（2 回試行）: EmphasisShortageError: 太字 `**X**` だけで `==マーカー==` も `__下線__` も使われていません。記事に数値・結論・規模があれば `==マーカー==` を、発表・公開・採用・買収など動作があれば `__下線__` を最低 1 つ入れてください。
```

#### Qwen3.6-35B-A3B (IQ3_XXS) 出力（39.3s）

- **score / importance / event_type**: 85 / high / release
- **summary**: ==6月30日==までに社内の **Claude Code** ライセンスをほぼすべて解約し、開発者に自社 **GitHub Copilot CLI** の利用へ移行するよう指示した。公式にはツールチェーンの統一だが、決算日直前というタイミングから実態は **AI 利用コスト削減** とみられる。ただし **Anthropic** モデル自体の利用は制限されないため、完全な決別ではない。
- **summary_points**:
  - ==6月30日==を期限に **Claude Code** のライセンス解約を実施し、エンジニアのツール選択を自社製品へ誘導する方針を決定した。
  - 決算締め切り直前の措置であることから、公式な理由である「統合」に加え、急増する **AI 利用コスト** を抑えるための実利的な判断が含まれているとみられる。
  - **GitHub Copilot CLI** は **Anthropic** のモデルも内包しており、競合ツールの排除ではなく自社エコシステムの強化を目的とした戦略的シフトである。
- **rationale**:
  - **buzz**: Microsoft が自社開発の GitHub Copilot CLI に移行を強制し、Anthropic の Claude Code のライセンスを解約する動きは、AI ツール競争の激化と内部コスト削減の両面から注目される。
  - **impact**: エンジニアのツール選定が直接的なビジネス影響（Copilot の販促・Claude の利用制限）に直結しており、競合他社や他業界への波及効果が大きい。
  - **importance**: AI ツール市場での覇権争いにおける重要な一手であり、企業内の AI スペンディング最適化の事例としても高い重要性を持つ。


### 4. Claude AI Down for Users as Anthropic Confirms Outage

- **publisher**: https://sqmagazine.co.uk/claude-ai-down-outage-june-2026/
- **category / event_type (ground truth)**: model / incident
- **本文文字数（再取得時点）**: 3000

#### flash 出力

- **score / importance / event_type**: 85 / high / incident
- **summary**: **Anthropic** の **Claude AI** サービスが ==2026年6月2日== に広範な障害を__経験__し、**Claude AI**、**Claude Console**、**Claude API**、**Claude Code** など複数のサービスで高いエラーレートが__発生__しました。**DownDetector** での報告急増を受け、**Anthropic** は問題の原因を__特定__し、__修正をロールアウト__していると発表。企業や開発者を含む多くのユーザーに影響が出ました。
- **summary_points**:
  - **Claude AI** サービスが ==2026年6月2日== に広範な障害を__経験__。
  - **DownDetector** で 2:19 AM 東部時間頃から障害報告が__急増__。
  - **Anthropic** は **Claude AI** など複数のサービスで高いエラーレートを__確認__。
  - **Anthropic** は問題の原因を__特定__し、__修正をロールアウト__中と発表。
- **rationale**:
  - **importance**: **Claude AI** は主要なAIプラットフォームであり、そのサービス障害は広範囲のユーザーに影響を与えるため、重要性は高いと判断しました。
  - **impact**: 企業や開発者を含む多くのユーザーが日常業務で **Claude** を利用しており、短時間の停止でも業務に大きな支障をきたすため、影響は大きいと判断しました。
  - **buzz**: 主要AIプラットフォームの障害は常に注目度が高く、SNSでも話題になりやすいため、話題性も高いと判断しました。

#### flash-lite 出力

- **score / importance / event_type**: 75 / high / incident
- **summary**: **Claude AI** は **2026年6月2日**、複数のサービスで大規模な障害が発生し、ユーザーが利用できない状況に __見舞われました__。**Anthropic** はエラー率の上昇を認め、復旧作業を進めました。この障害は **Claude AI、Claude Console、Claude API、Claude Code** など、個人向け・開発者向けサービスに __影響__ しました。
- **summary_points**:
  - **Claude AI** が **2026年6月2日**に大規模障害、**Anthropic** がエラー率上昇を __確認__。
  - 障害は **Claude AI、Claude Console、Claude API、Claude Code** など広範囲に __影響__。
  - **DownDetector** では午前2時19分（東部時間）頃から報告が __急増__。
  - 多くのビジネスや開発者が利用する **AIサービス** の障害は、即座に __注目__ を集める。
- **rationale**:
  - **importance**: AIサービスの広範な障害は、多くのユーザーやビジネスに直接影響を与えるため、重要度が高いと判断しました。
  - **impact**: Claude AIおよび関連サービスが利用不能になったことで、ユーザーの業務や開発活動に一時的な支障が出たと考えられます。
  - **buzz**: AIアシスタントの障害は、その依存度の高さから、発生するとSNSやニュースで広く話題になりやすい傾向があります。

#### qwen3:14b 出力（10.4s）

- **score / importance / event_type**: 65 / mid / incident
- **summary**: **Anthropic** は 2026 年 6 月 2 日に **Claude AI** のサービス停止を確認し、**複数のモデルとサービス**でエラー率が上昇していると発表。**DownDetector** によると、**2:19 AM Eastern Time** にユーザーからの報告が急増し、**クラウド API、コンソール、コード**なども影響を受けた。**技術的な原因**は明かされていないが、**修正が進行中**である。
- **summary_points**:
  - **Anthropic** は **Claude AI** の **サービス停止** を確認し、**複数のモデルとサービス** でエラーが発生している。
  - ==2:19 AM Eastern Time== に **DownDetector** で **ユーザーからの報告が急増** し、**サービス障害** が拡大した。
  - **Claude API、コンソール、コード** など **複数のサービス** が影響を受けた。
  - **技術的な原因** は明かされていないが、**修正が進行中** である。
- **rationale**:
  - **importance**: mid
  - **impact**: AI プラットフォームのサービス停止は、開発者や企業にとって影響が大きく、注目度が高い。ただし、技術的な詳細が不明なため、重要性は中程度。
  - **buzz**: AI 関連のサービス障害は、SNSやメディアで話題になりやすく、一定の注目を集めている。

#### Qwen3.6-35B-A3B (IQ3_XXS) 出力（35.9s）

- **score / importance / event_type**: 65 / mid / incident
- **summary**: **Anthropic**の人工知能サービス**Claude AI**が2026年6月2日早朝に広範囲で停止した。DownDetectorでは米東部時間午前2時19分頃から報告が急増し、**Claude Console**や**API**など複数の製品でエラー率が上昇。同社は公式ステータスページで調査中であることを発表後、原因を特定し__修正を実施__した。消費者向けと開発者向けの両方で影響があったことが確認されている。
- **summary_points**:
  - **Anthropic**は**Claude AI**の障害について__公式ステータスページで確認__し、調査から原因特定まで迅速に対応した。
  - 米東部時間6月2日午前2時19分頃からDownDetectorでの報告が急増し、SNSでも問題が拡散した。
  - **Claude Console**や**API**など複数のサービスでエラーが発生し、__修正プログラムを展開__して復旧に向けた作業が進められた。
- **rationale**:
  - **buzz**: **Anthropic**の**Claude AI**が広範なサービス停止を引き起こし、開発者や一般ユーザーに大きな影響を与えた。DownDetectorでの報告急増やSNSでの拡散から、高い関心を集めている。
  - **impact**: APIやConsoleなど多様な製品でエラー率が上昇し、業務継続性に影響。原因特定と修正作業が行われたが、インフラの安定性に対する懸念を残す。
  - **importance**: 主要AIサービスの障害は業界内の信頼性と運用実態を示す指標となる。ただし、復旧までの時間が短く、長期的なビジネスへの致命的打撃とはみなしにくい。


### 5. Cognition’s Scott Wu says AI coding agents shouldn’t replace humans

- **publisher**: https://techcrunch.com/2026/05/29/cognitions-scott-wu-says-ai-coding-agents-shouldnt-replace-humans/
- **category / event_type (ground truth)**: agent / release
- **本文文字数（再取得時点）**: 3000

#### flash 出力

- **score / importance / event_type**: 85 / high / funding
- **summary**: **Cognition**の**Scott Wu** CEOは、==10億ドル==の資金調達と==260億ドル==の評価額で注目を集める**AIコーディングエージェント**「**Devin**」について、人間を__置き換える__のではなく「相棒」として__支援する__存在であると__述べた__。同社は「自己駆動型ソフトウェア開発」への移行を__目指す__一方で、**Wu**氏はプログラマーが仕事を失うことを望んでいない。**Devin**は**Cognition**社内でコミットされるコードの==89%==を__担当__し、プログラマーが嫌うメンテナンス作業を__自動化__することで、彼らを「苦役から解放し、より創造的な活動に集中させる」ことを__目指している__。
- **summary_points**:
  - **Cognition**の**Scott Wu** CEOは、**AIコーディングエージェント**「**Devin**」が人間を__置き換える__のではなく「相棒」として__支援する__と__強調__。
  - 同社は最近、==10億ドル==を調達し、評価額は==260億ドル==に__達した__。
  - **Devin**は**Cognition**社内でコミットされるコードの==89%==を__担当__し、主にメンテナンス作業を__自動化__。
  - **Wu**氏は、**Devin**がプログラマーを「多くの苦役から解放し、より多くのことができるようにする」と__説明__。
- **rationale**:
  - **importance**: **Cognition**の巨額資金調達と、**AIエージェント**の役割に関するCEOの発言は、業界の方向性を示す上で非常に重要です。
  - **impact**: ソフトウェア開発における**AIエージェント**の導入と、それによる開発者の働き方の変化に大きな影響を与える可能性があります。
  - **buzz**: **Cognition**と**Devin**は高い注目度があり、**AI**による雇用への影響は社会的に大きな関心事であるため、話題性が高いです。

#### flash-lite 出力

- **score / importance / event_type**: 85 / high / release
- **summary**: AIコーディングエージェント開発のCognition、CEOのScott Wu氏は、同社のAI「Devin」が人間のプログラマーを代替するものではないと明言した。Wu氏は、Devinはあくまで開発を支援する「相棒」であり、プログラミングの楽しさを奪うものではないと強調。同社ではDevinがエンジニアのコミットコードの89%を占めるが、これは主に保守作業などの「骨の折れる」タスクを担うためだという。
- **summary_points**:
  - **Cognition** CEOのScott Wu氏は、AIコーディングエージェント「**Devin**」は人間を代替するものではないと主張。
  - Wu氏はDevinを、開発者がより多くのものを作るのを助ける「**相棒**」と位置づけている。
  - 同社では、**Devin**がエンジニアのコミットコードの==89%==を占める。
  - AIエージェントは、プログラマーを「**骨の折れる**」作業から解放し、より創造的な作業に集中させることを目的とする。
- **rationale**:
  - **importance**: AI開発における人間とAIの関係性についてのCEOの発言であり、将来のソフトウェア開発のあり方に影響を与える可能性があるため。
  - **impact**: AIコーディングエージェントが人間の職を奪うのではないかという懸念に対し、開発元自身が否定的な見解を示したことは、業界の議論に一石を投じる。
  - **buzz**: Cognitionは最近、==10億ドル==の資金調達に成功し、AIコーディングエージェント「Devin」は大きな注目を集めている。CEOの発言は、この注目度の高さを反映している。

#### qwen3:14b 出力（26.4s）

- **score / importance / event_type**: 85 / high / release
- **summary**: **Cognition** の CEO **Scott Wu** は、AI コーディングエージェント **Devin** が人間のプログラマーを置き換えることはないと強調。**Devin** は、プログラマーが「より多くのことを成し遂げるための仲間」として位置づけられている。また、**Cognition** は **Devin** が同社のエンジニアが書いたコードの **89%** を担当していると明かし、**Devin** が長期間にわたるメンテナンスタスクを担っていると説明。**Devin** は、プログラマーが「苦手とする作業」から解放し、より創造
- **summary_points**:
  - **Cognition** の **Scott Wu** は、**Devin** が人間を置き換えることはないと明言し、__仲間__ としての役割を強調。
  - **Devin** は **Cognition** のエンジニアが書いたコードの ==89%== を担当しており、メンテナンスタスクを担っている。
  - **Scott Wu** は、プログラマーが「苦手とする作業」から解放され、創造的な作業に集中できると説明。
  - **Devin** は、ソフトウェア開発の抽象化を進める新たな層として位置づけられている。
  - **Scott Wu** は、プログラミングの楽しさを失わせたくないという姿勢を示している。
- **rationale**:
  - **importance**: high
  - **impact**: AI コーディングエージェントの将来像に直接関係する声明であり、業界全体に影響を与える可能性がある。
  - **buzz**: AI が人間の職を置き換えるという懸念が高まる中、**Cognition** が明確な姿勢を示したことで注目を集めている。

#### Qwen3.6-35B-A3B (IQ3_XXS) 出力（47.7s）

- **score / importance / event_type**: 65 / mid / release
- **summary**: **Cognition** の **Scott Wu** CEOは、同社が調達した **$10億**資金を背景に、AIコーディングエージェントの役割について明確なビジョンを示した。**Devin** が開発現場で果たす役割について「人間を__置き換える__ものではない」と強調し、プログラマーにとっての__支援者__としての位置づけを繰り返し主張している。しかし、同社内部ではエンジニアによるコミットの **89%** を **Devin** が占めており、その実態は高度な自動化を進めるものとなっている。Wu氏は、AIが__冗長なタスク__から開発者を解放し
- **summary_points**:
  - **Cognition** の **Scott Wu** CEOは、同社が調達した ==$10億== 資金を背景に、AIコーディングエージェントの役割について明確なビジョンを示した。
  - **Devin** が開発現場で果たす役割について「人間を__置き換える__ものではない」と強調し、プログラマーにとっての__支援者__としての位置づけを主張している。
  - 同社内部ではエンジニアによるコミットの ==89%== を **Devin** が占めており、その実態は高度な自動化を進めるものとなっていると報じられている。
  - Wu氏は、AIが__冗長なタスク__から開発者を解放し、創造的な__ソフトウェア構築の喜び__を維持できる環境を整えることを目標としている。
- **rationale**:
  - **buzz**: **Cognition** の **Devin** が **$10億**調達と相まって注目される中、CEOはAIが人間を排除するのではなく__支援ツール__として機能すると明言。
  - **impact**: 開発現場でのAI活用姿勢を示す重要発言だが、同社内で**89%**のコードがAIによって書かれているという現実との整合性が問われる点で限定的な影響にとどまる。
  - **importance**: 業界全体の雇用不安を和らげるメッセージ性は高いものの、Cognition社内の運用実態（**Devin**による大多数のコミット）と矛盾する側面があり、普遍的な基準値としてmid評価とする。


## ローカル実測スループット

- **qwen3:14b**: 1 件平均 **18.4s**（2 件・初回はモデルロードで割高）／ 76 件直列推定 **約 23 分**（RPM/RPD 天井なし）
- **Qwen3.6-35B-A3B (IQ3_XXS)**: 1 件平均 **44.0s**（4 件・初回はモデルロードで割高）／ 76 件直列推定 **約 56 分**（RPM/RPD 天井なし）


## 評価所感（4-way / Claude 分析）

| 観点 | flash | flash-lite | qwen3:14b | 35B-A3B | 判定 |
|---|---|---|---|---|---|
| 完走率（emphasis契約下） | 4/4 | 4/4 | **2/4 ドロップ** | **4/4** | 35B 堅牢 / 14b 脆 |
| summary 完結性 | 完結 | 完結 | s5 語中切れ | s5 語中切れ | **両ローカルとも maxLength:280 で長文記事は切れる** |
| 強調記法の質 | 適切 | 適切 | 出せず脱落 | 実語へ適切付与 | 35B > 14b |
| rationale 論理性 | 高 | 高 | 標準 | **高（矛盾点まで批判的に指摘）** | 35B ◎ |
| score 傾向 | 80-85 | 75-85 | 65-85 | 65-85（保守的） | 採用率影響なし（≥65・SCORE_MIN=50） |
| event_type | 妥当 | 妥当 | 妥当 | 妥当 | 拮抗（s3 regulation は全モデル誤＝プロンプト課題） |
| 76件直列スループット | API | API | **約23分** | 約56分 | 14b が 2.4倍速 |

### 所感
1. **今回 qwen3:14b は emphasis 契約で 2/4 ドロップ**（前回 2-way は通過＝run間ばらつき）。**ただしこれは強調を LLM に出させている前提の失敗**。決定通り強調をコード付与へ移せばこの脱落は消える＝14b の真の失敗率はこの数字より低い。
2. **35B-A3B は emphasis 込みでも 4/4 堅牢**・実語へ正しくマーカー付与・rationale が最も分析的（s5 で「人間を代替しない」発言と「89%が AI コミット」の矛盾まで指摘）。**品質は flash-lite 以上**の場面あり。代償は **~44s/件（76件で約56分）と 14b の 2.4倍遅い**。
3. **maxLength:280 は両ローカル共通の地雷**。長文記事(s5)で 14b・35B とも summary が語中切れ。flash は自然に 280字未満に収まる。→ ローカル用にスキーマ maxLength を緩める(280→~400)か summary 長を強めに指示する。
4. **35B は essay フェーズの指定モデルでもある**ため、35B で抽出も essay も一本化すれば VRAM 運用が単純（1モデル常駐・スワップ無し）。

### Claude 推奨
- 先に **(a) 強調のコード付与化（rewrite_emphasis.py 本線化）+ (b) maxLength 緩和** を実装し、**ハイブリッド（失敗/GPU占有時に Gemini フォールバック）** で配線（LLM境界1箇所なので config スイッチで可逆）。
- 抽出モデルは速度↔品質のダイヤル: **夜間バッチ運用なら 35B 一本化（品質・堅牢・運用単純）、抽出を速く回したいなら qwen3:14b**。

## 評価所感（手動追記欄）

- summary 完結性（maxLength 語中切れの有無）: 
- 事実精度 / 要点適切性: 
- rationale 論理性: 
- score / importance 妥当性: 
- event_type 分類精度: 
- 14b vs 35B どちらが抽出に優れるか: 


## 推奨判断

- [ ] qwen3:14b に置換
- [ ] Qwen3.6-35B-A3B に置換
- [ ] flash-lite 維持
- [ ] ハイブリッド（通常ローカル・失敗/GPU占有時に Gemini フォールバック）
