import asyncio
import logging
import random
import time
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple RPM/TPM tracker with backoff helpers."""

    def __init__(self) -> None:
        settings = get_settings()
        self.rpm_limit = settings.llm_rpm_limit
        self.tpm_limit = settings.llm_tpm_limit
        self.max_retries = settings.llm_max_retries
        self._lock = asyncio.Lock()
        self._request_timestamps: list[float] = []
        self._token_window: list[tuple[float, int]] = []
        self._cooldown_until: float = 0.0

    async def acquire(self, estimated_tokens: int = 0) -> None:
        # A single call may legitimately exceed TPM (large summarize). Cap the
        # reservation so we never spin forever when estimate > limit.
        est = max(0, int(estimated_tokens))
        if est > self.tpm_limit:
            logger.warning(
                "LLM estimate %s tokens exceeds TPM limit %s; capping reservation",
                est,
                self.tpm_limit,
            )
            est = self.tpm_limit

        while True:
            wait_for = 0.0
            async with self._lock:
                now = time.monotonic()
                if now < self._cooldown_until:
                    wait_for = self._cooldown_until - now
                else:
                    self._prune(now)
                    if len(self._request_timestamps) >= self.rpm_limit:
                        wait_for = 60 - (now - self._request_timestamps[0]) + 0.05
                    else:
                        tokens_used = sum(t for _, t in self._token_window)
                        if self._token_window and tokens_used + est > self.tpm_limit:
                            wait_for = 60 - (now - self._token_window[0][0]) + 0.05
                        else:
                            # Empty window or enough budget — allow the call
                            self._request_timestamps.append(now)
                            if est:
                                self._token_window.append((now, est))
                            return
            await asyncio.sleep(max(wait_for, 0.05))

    def record_usage(self, tokens: int) -> None:
        now = time.monotonic()
        self._token_window.append((now, tokens))
        self._prune(now)

    def set_retry_after(self, seconds: float) -> None:
        self._cooldown_until = max(self._cooldown_until, time.monotonic() + seconds)

    def backoff_seconds(self, attempt: int, retry_after: Optional[float] = None) -> float:
        if retry_after is not None:
            return float(retry_after)
        base = min(2**attempt, 30)
        return base + random.uniform(0, 0.5)

    def _prune(self, now: float) -> None:
        cutoff = now - 60
        self._request_timestamps = [t for t in self._request_timestamps if t >= cutoff]
        self._token_window = [(t, n) for t, n in self._token_window if t >= cutoff]


_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter
