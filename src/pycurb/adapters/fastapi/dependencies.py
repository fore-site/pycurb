from fastapi import Request, HTTPException
from typing import Callable
from pycurb.core import AsyncRateLimiter, RateLimitResult
from .extractors import ip_extractor

async def rate_limit_dep(
    request: Request,
    limiter: AsyncRateLimiter,
    rule_name: str,
    key_extractor: Callable[[Request], str] = ip_extractor,
) -> RateLimitResult:
    """
    FastAPI dependency that applies a rate limit rule.
    Raises HTTP 429 if limit exceeded.
    """
    key = key_extractor(request)
    result = await limiter.check(key, rule_name)
    if not result.allowed:
        # Compute Retry-After header value
        import time
        retry_after = max(1, int(result.reset_at - time.time()))
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
    # Optionally attach result to request state for later use (e.g., add headers)
    request.state.rate_limit_result = result
    return result