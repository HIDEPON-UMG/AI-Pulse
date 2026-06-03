"""パイプラインの可変パラメータ（仕様書 playground の仮置き値）。

値の根拠: docs/specs/2026-06-02_ai-pulse-architecture.html の「パラメータ」タブ。
playground のスライダーで調整し「プロンプトとしてコピー」で確定したら本ファイルを上書きする。
パラメータを 1 箇所に集約することで、収集系コードに数値を直書きしない。
"""

SCORE_MIN = 50             # ニュース性スコア下限（これ未満は掲載しない）
BREAKING_PER_CATEGORY = 5  # 速報 1 カテゴリあたり収集件数
RECHECK_DAYS = 30          # カルテ再評価の既定周期（日）
DEEP_POLL_MINUTES = 5      # NotebookLM deep のポーリング間隔（分）
RECENT_EVENTS_CAP = 10     # カルテに backlink する最新デルタ件数の上限
