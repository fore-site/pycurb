from typing import Union, List, Callable
from fastapi import Request, HTTPException
from pycurb.core import AsyncRateLimiter, RateLimitResult
from .extractors import ip_extractor
import time

def rate_limiter(
    limiter: AsyncRateLimiter,
    rule_name: Union[str, List[str]],
    key_extractor: Callable[[Request], str] = ip_extractor,
):
    """
    Factory that creates a FastAPI dependency for rate limiting.
    """
    async def dependency(request: Request) -> RateLimitResult:
        key = key_extractor(request)
        result = await limiter.check(key, rule_name)
        if not result.allowed:
            retry_after = max(1, int(result.reset_at - time.time()))
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )
        request.state.rate_limit_result = result
        return result
    return dependency