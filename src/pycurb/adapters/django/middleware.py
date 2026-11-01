from collections.abc import Callable
from typing import List, Union

from django.http import HttpRequest, JsonResponse
from django.http.response import HttpResponseBase

from pycurb.core import AsyncRateLimiter, RateLimiter
from pycurb.core.models import RateLimitHeaders

from .extractors import ip_extractor


def create_rate_limit_middleware(
    limiter: Union[RateLimiter, AsyncRateLimiter],
    rule_name: Union[str, List[str]],
    key_extractor: Callable[[HttpRequest], str] = ip_extractor,
) -> type:
    """
    Factory that returns a Django middleware class for global rate limiting.
    Works with sync limiter for now.
    If you use async limiter, you must ensure it is compatible with sync calls
    (e.g., by using asyncio.run). For simplicity, use RateLimiter.
    """
    if isinstance(limiter, AsyncRateLimiter):
        raise TypeError(
            "Out-of-box Middleware only supports a sync limiter for now. Use RateLimiter."
        )

    class RateLimitMiddleware:
        def __init__(
            self, get_response: Callable[[HttpRequest], HttpResponseBase]
        ) -> None:
            self.get_response = get_response
            self.limiter = limiter
            self.rule_name = rule_name
            self.key_extractor = key_extractor

        def __call__(self, request: HttpRequest) -> HttpResponseBase:
            key = self.key_extractor(request)
            result = self.limiter.check(key, self.rule_name)
            if not result:
                headers = RateLimitHeaders.from_result(result)
                status_code = 503 if result.storage_unavailable else 429
                detail = (
                    "Rate limiter unavailable"
                    if result.storage_unavailable
                    else "Rate limit exceeded"
                )
                response = JsonResponse({"detail": detail}, status=status_code)
                for name, value in headers.to_dict().items():
                    response[name] = value
                return response
            response = self.get_response(request)
            headers = RateLimitHeaders.from_result(result)
            for name, value in headers.to_dict().items():
                response[name] = value
            return response

    return RateLimitMiddleware
