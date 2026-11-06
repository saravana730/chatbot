import asyncio
import logging
from typing import AsyncIterator, Optional

from groq import APIStatusError, AsyncGroq, RateLimitError

from app.core.config import get_settings
from app.llm.base import LLMMessage, LLMProvider, LLMResponse
from app.llm.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)


class GroqProvider(LLMProvider):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.groq_api_key:
            logger.warning("GROQ_API_KEY is empty; LLM calls will fail until set")
        # Hard request timeout so large ingest summaries cannot hang forever
        self.client = AsyncGroq(
            api_key=settings.groq_api_key or "missing",
            timeout=120.0,
        )
        self.model = settings.groq_model
        self.limiter = get_rate_limiter()
        self.max_retries = settings.llm_max_retries

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: Optional[int] = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        settings = get_settings()
        max_tokens = max_tokens or settings.llm_output_reserve
        payload = [{"role": m.role, "content": m.content} for m in messages]
        estimated = sum(len(m.content) // 4 for m in messages) + max_tokens

        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            await self.limiter.acquire(estimated)
            try:
                resp = await self.client.chat.completions.create(
                    model=self.model,
                    messages=payload,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                content = resp.choices[0].message.content or ""
                usage = resp.usage
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                self.limiter.record_usage(prompt_tokens + completion_tokens)
                return LLMResponse(
                    content=content,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    model=self.model,
                )
            except RateLimitError as exc:
                last_exc = exc
                retry_after = _extract_retry_after(exc)
                wait = self.limiter.backoff_seconds(attempt, retry_after)
                self.limiter.set_retry_after(wait)
                logger.warning("Groq rate limited; retry in %.2fs", wait)
                await asyncio.sleep(wait)
            except APIStatusError as exc:
                last_exc = exc
                if exc.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    retry_after = _extract_retry_after(exc)
                    wait = self.limiter.backoff_seconds(attempt, retry_after)
                    if exc.status_code == 429:
                        self.limiter.set_retry_after(wait)
                    logger.warning("Groq HTTP %s; retry in %.2fs", exc.status_code, wait)
                    await asyncio.sleep(wait)
                    continue
                raise
        raise RuntimeError(f"Groq request failed after retries: {last_exc}") from last_exc

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: Optional[int] = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        """Stream tokens. Retries only before first token is yielded."""
        settings = get_settings()
        max_tokens = max_tokens or settings.llm_output_reserve
        payload = [{"role": m.role, "content": m.content} for m in messages]
        estimated = sum(len(m.content) // 4 for m in messages) + max_tokens

        stream = None
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            await self.limiter.acquire(estimated)
            try:
                stream = await self.client.chat.completions.create(
                    model=self.model,
                    messages=payload,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True,
                )
                break
            except (RateLimitError, APIStatusError) as exc:
                last_exc = exc
                status = getattr(exc, "status_code", 429)
                if status not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    raise
                wait = self.limiter.backoff_seconds(attempt, _extract_retry_after(exc))
                await asyncio.sleep(wait)
        if stream is None:
            raise RuntimeError(f"Groq stream failed: {last_exc}") from last_exc

        async for event in stream:
            delta = event.choices[0].delta.content if event.choices else None
            if delta:
                yield delta


def _extract_retry_after(exc: Exception) -> Optional[float]:
    headers = getattr(exc, "headers", None) or {}
    value = None
    if hasattr(headers, "get"):
        value = headers.get("retry-after") or headers.get("Retry-After")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_provider: Optional[GroqProvider] = None


def get_llm_provider() -> GroqProvider:
    global _provider
    if _provider is None:
        _provider = GroqProvider()
    return _provider
