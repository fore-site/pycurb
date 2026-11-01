from collections.abc import Awaitable, Callable
from typing import List, Union

from fastapi import HTTPException, Request, Response
from pycurb.core import AsyncRateLimiter, RateLimitResult
from pycurb.core.models import RateLimitHeaders

from .extractors import ip_extractor


def rate_limiter(
    limiter: AsyncRateLimiter,
    rule_name: Union[str, List[str]],
    key_extractor: Callable[[Request], str] = ip_extractor,
) -> Callable[[Request, Response], Awaitable[RateLimitResult]]:
    """
    Factory that creates a FastAPI dependency for rate limiting.
    """

    async def dependency(request: Request, response: Response) -> RateLimitResult:
        key = key_extractor(request)
        result = await limiter.check(key, rule_name)

        headers = RateLimitHeaders.from_result(result).to_dict()
        if result.storage_unavailable:
            raise HTTPException(
                status_code=503,
                detail="Rate limiter unavailable",
                headers=headers,
            )

        if not result:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers=headers,
            )

        request.state.rate_limit_result = result
        for name, value in headers.items():
            response.headers[name] = value
        return result

    return dependency
