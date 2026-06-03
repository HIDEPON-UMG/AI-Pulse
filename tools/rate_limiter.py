"""トークンバケット式のレート制限。Gemini Free Tier (15 RPM) に対する 80% マージン (12 RPM) で運用。

なぜ重要か（意図）:
  Free Tier の 15 RPM は短時間バーストで簡単に踏み抜く。Python 側で 1 リクエスト = 1 トークン消費の
  バケットを 1 箇所に集約することで、collect_rss から llm_gemini を呼ぶたびに acquire を通すだけで
  バースト 429 を構造的に防ぐ。実時間ベース（time.monotonic）なので、複数バッチ・夜間長時間実行でも
  正しく rate に収束する。
"""
from __future__ import annotations

import time
from threading import Lock


class TokenBucket:
    """RPM ベースのトークンバケット。

    rate_per_sec   = max_tokens / period（period=60 sec）
    capacity       = max_tokens (バースト上限)。Gemini 15 RPM なら capacity=12, rate=12/60
    acquire(n=1)   = n トークン消費。足りない時は補充されるまで time.sleep でブロック。
    """

    def __init__(self, *, rpm: int, capacity: int | None = None):
        if rpm <= 0:
            raise ValueError(f"rpm must be > 0, got {rpm}")
        self.rate_per_sec = rpm / 60.0
        self.capacity = float(capacity if capacity is not None else rpm)
        self.tokens = self.capacity      # 起動直後は満タン
        self.last = time.monotonic()
        self._lock = Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_sec)
            self.last = now

    def acquire(self, n: int = 1) -> float:
        """n トークン取得。返り値は実際に待たされた秒数（テスト用）。"""
        if n > self.capacity:
            raise ValueError(f"requested {n} > capacity {self.capacity}")
        waited = 0.0
        while True:
            with self._lock:
                self._refill()
                if self.tokens >= n:
                    self.tokens -= n
                    return waited
                needed = n - self.tokens
                wait = needed / self.rate_per_sec
            time.sleep(wait)
            waited += wait
