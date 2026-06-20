from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from typing import Callable, Optional
from pycurb.core import AsyncRateLimiter
from pycurb.core.models import RateLimitHeaders
from .extractors import ip_extractor


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware to apply a global rate limit rule to all requests.
    Optionally exclude certain paths.
    """

    def __init__(
        self,
        app: ASGIApp,
        limiter: AsyncRateLimiter,
        rule_name: str,
        key_extractor: Callable[[Request], str] = ip_extractor,
        exclude_paths: Optional[list[str]] = None,
    ):
        super().__init__(app)
        self.limiter = limiter
        self.rule_name = rule_name
        self.key_extractor = key_extractor
        self.exclude_paths = exclude_paths or []

    async def dispatch(self, request: Request, call_next):
        # Skip excluded paths
        for path in self.exclude_paths:
            if request.url.path.startswith(path):
                return await call_next(request)

        key = self.key_extractor(request)
        result = await self.limiter.check(key, self.rule_name)

        if not result.allowed:
            headers = RateLimitHeaders.from_result(result)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers=headers.to_dict(),
            )

        # Add rate limit headers to response
        response = await call_next(request)
        headers = RateLimitHeaders.from_result(result)
        for name, value in headers.to_dict().items():
            response.headers[name] = value
        return response
