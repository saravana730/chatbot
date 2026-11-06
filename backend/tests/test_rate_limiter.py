import asyncio

from app.llm.rate_limiter import RateLimiter


def test_acquire_allows_when_estimate_exceeds_tpm():
    limiter = RateLimiter()
    limiter.tpm_limit = 100
    limiter.rpm_limit = 30

    async def run() -> None:
        # Must not hang forever when a single estimate > TPM
        await asyncio.wait_for(limiter.acquire(500), timeout=1.0)

    asyncio.run(run())
