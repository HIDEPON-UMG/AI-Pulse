"""パイプラインの可変パラメータ（仕様書 playground の仮置き値）。

値の根拠: docs/specs/2026-06-02_ai-pulse-architecture.html および
docs/specs/2026-06-03_collection-pipeline-redesign.html の「パラメータ」タブ。
playground のスライダーで調整し「プロンプトとしてコピー」で確定したら本ファイルを上書きする。
パラメータを 1 箇所に集約することで、収集系コードに数値を直書きしない。
"""

# --- サイト公開 URL（OGP 絶対 URL に必須） ---
# Twitter / Facebook の OGP パーサは og:image / og:url に絶対 URL を要求する。
# GitHub Pages の公開先を一次ソースとして 1 箇所に持ち、Jinja から `site_url` で参照する。
# 末尾スラッシュ必須（テンプレが `{{ site_url }}og-image.png` のように連結するため）。
SITE_URL = "https://hidepon-umg.github.io/AI-Pulse/"

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
# 本文文字数: 2026-06-04 eval 追補10 で 3000→5000 に拡大（8000 一律は隣接数値の混同誘発で却下）。
# Qwen3.6-35B-A3B は長文に強く、5000 字までは要点抽出が安定する（grounded プロンプト併用）。
MAX_BODY_CHARS = 5000
MIN_BODY_CHARS = 200                # これ未満はドロップ（paywall / 404 / カード型本文の事故防止）

# --- ローカル LLM (Ollama) バックエンド（2026-06-04 eval 確定・2026-06-05 本配線） ---
# Ollama 0.30.3 / RTX5080 16GB。Qwen3.6-35B-A3B は盲検ジャッジ総合 3.80/5 > flash-lite 3.38 で品質一位。
# 狙いは API クォータ非依存・オフライン自走 + データが Google 学習に使われない安全側（コスト動機なし）。
# 本番切替は llm_hybrid 経由で 1 行入替で済むよう境界 1 箇所集約（feedback_check_design_principles §2）。
OLLAMA_HOST = "http://localhost:11434"
# hf.co GGUF は `/api/generate` だと chat template 欠落で `/api/chat`(messages) 必須（追補10 注意）。
OLLAMA_MODEL = "hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-IQ3_XXS"
OLLAMA_TEMPERATURE = 0.1            # 事実忠実性を優先（眼の前の本文だけを根拠に出させる）
OLLAMA_TIMEOUT_SEC = 180           # 初回はモデルロードで時間がかかる。warm 後は ~30s/件
OLLAMA_MAX_RETRIES = 2             # 接続/空応答/パース失敗の短バックオフ回数（実回数: 2 = 計 3 試行）

# --- ハイブリッド LLM 構成（2026-06-05 追加・追補11 で配線） ---
# 通常パス = ローカル (Ollama Qwen3.6-35B-A3B)、失敗 / GPU 占有時に Gemini フォールバック。
# 境界 1 箇所 (tools/llm_hybrid.generate_event_extras) で切替を locked-in（契約テスト test_llm_hybrid.py）。
# - local_first  : 既定。GPU 非占有なら local 試行 → LLMError で Gemini にフォールバック
# - gemini_first : Gemini 試行 → 失敗で local（クォータが温存される A/B 比較用）
# - gemini_only  : 常時 Gemini（Ollama 全停止時の暫定回避 / ベースライン比較用）
# - local_only   : 常時 local（テスト用・Gemini を絶対呼ばせたくない時の locked-in）
HYBRID_MODE = "local_first"
# GPU メモリ占有閾値（MB）。ComfyUI 等の他 GPU タスクが「Qwen3.6-35B-A3B を載せる余地が無い」
# レベルで VRAM を埋めている時に限り local をスキップして Gemini に流す。
# 2026-06-06 改定: 6000 → 12000。理由: 旧値 6000 では ComfyUI が軽く立っているだけで
# `_gpu_busy()=True` に倒れ、6/3-6/6 で Gemini フォールバック率 91.2% (= 想定 20% の 4.5 倍) を
# 実測した (Cloud Monitoring と Ollama server.log の照合で確定)。RTX5080 16GB のうち 35B-A3B
# UD-IQ3_XXS は ~10-12GB 消費するため、残 4-6GB を切るまでは local 試行を許す。Ollama が VRAM
# 不足で OOM したら llm_hybrid 層が LLMError → Gemini で救うので可逆。
HYBRID_GPU_THRESHOLD_FB_MB = 12000
# llm_local 側で「接続/空応答/JSON パース失敗」のバックオフ回数は OLLAMA_MAX_RETRIES に集約済。
# hybrid 層では追加リトライせず、LLMError を 1 度でも受けたら即 Gemini にフォールバックする。
HYBRID_LOCAL_RETRY_BEFORE_FALLBACK = OLLAMA_MAX_RETRIES
