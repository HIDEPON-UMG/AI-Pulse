"""パイプラインの可変パラメータ（仕様書 playground の仮置き値）。

値の根拠: docs/specs/2026-06-02_ai-pulse-architecture.html および
docs/specs/2026-06-03_collection-pipeline-redesign.html の「パラメータ」タブ。
playground のスライダーで調整し「プロンプトとしてコピー」で確定したら本ファイルを上書きする。
パラメータを 1 箇所に集約することで、収集系コードに数値を直書きしない。
"""

SCORE_MIN = 50             # ニュース性スコア下限（これ未満は掲載しない）
BREAKING_PER_CATEGORY = 5  # 速報 1 カテゴリあたり収集件数
RECHECK_DAYS = 30          # カルテ再評価の既定周期（日）
DEEP_POLL_MINUTES = 5      # NotebookLM deep のポーリング間隔（分）
RECENT_EVENTS_CAP = 10     # カルテに backlink する最新デルタ件数の上限

# --- Gemini API / 本文取得（2026-06-04 追加） ---
# Free Tier の最新値（2026-01 集計時点）:
#   gemini-2.5-flash      : 10 RPM / 250 RPD / 250K TPM
#   gemini-2.5-flash-lite : 15 RPM / 1000 RPD / 250K TPM
# 2025-12 に Google が Free Tier quota を 50-80% 削減済み。引継ぎ書の旧値 (15/1500) は無効。
GEMINI_MODEL = "gemini-2.5-flash-lite"  # output $0.40/1M（flash の約 1/6）・Free Tier RPD 1000・summary 2倍化と同時切替
GEMINI_RPM = 15                         # flash-lite の 15 RPM 上限（flash の 10 RPM から増枠）
GEMINI_TIMEOUT_SEC = 30             # 1 リクエストの上限
GEMINI_MAX_RETRIES = 2              # 429/5xx の指数バックオフ回数（実回数: 2 リトライ = 計 3 試行）
ARTICLE_FETCH_TIMEOUT = 12          # trafilatura / urllib の本文取得タイムアウト（秒）
MAX_BODY_CHARS = 3000               # Gemini に渡す本文の最大文字数（TPM 消費抑制）
MIN_BODY_CHARS = 200                # これ未満はドロップ（paywall / 404 / カード型本文の事故防止）

# --- ローカル LLM (Ollama) バックエンド（2026-06-04 追加・抽出のローカル置換検討用） ---
# Ollama 0.30.3 / RTX5080 16GB。qwen3:14b は指示遵守重視の抽出用（thinking モデル → think=false 必須）。
# 狙いは API クォータ非依存・オフライン自走（コスト面は flash-lite が既に $0.015/76件で差が無いため動機にならない）。
# 本番切替は 3-way eval (tools/eval_local_extraction.py) 合格後に collect_rss を配線する。
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "qwen3:14b"
OLLAMA_TEMPERATURE = 0.4            # Gemini 側 (0.4) と揃えて品質を同条件比較する
OLLAMA_TIMEOUT_SEC = 180           # 初回はモデルロードで時間がかかる。warm 後は ~10s/件
OLLAMA_MAX_RETRIES = 2             # 接続/空応答/パース失敗の短バックオフ回数（実回数: 2 = 計 3 試行）
