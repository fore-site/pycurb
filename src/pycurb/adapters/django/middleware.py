from django.http import JsonResponse
from typing import Callable, Union
from pycurb.core import RateLimiter, AsyncRateLimiter
from pycurb.core.models import RateLimitHeaders
from .extractors import ip_extractor

def create_rate_limit_middleware(
    limiter: Union[RateLimiter, AsyncRateLimiter],
    rule_name: str,
    key_extractor: Callable = ip_extractor,
):
    """
    Factory that returns a Django middleware class for global rate limiting.
    Works with sync limiter for now.
    If you use async limiter, you must ensure it is compatible with sync calls
    (e.g., by using asyncio.run). For simplicity, use RateLimiter.
    """
    if isinstance(limiter, AsyncRateLimiter):

        raise TypeError("Out-of-box Middleware only supports a sync limiter for now. Use RateLimiter.")

    class RateLimitMiddleware:
        def __init__(self, get_response):
            self.get_response = get_response
            self.limiter = limiter
            self.rule_name = rule_name
            self.key_extractor = key_extractor

        def __call__(self, request):
            key = self.key_extractor(request)
            result = self.limiter.check(key, self.rule_name)
            if not result.allowed:
                headers = RateLimitHeaders.from_result(result)
                response = JsonResponse({"detail": "Rate limit exceeded"}, status=429)
                for name, value in headers.to_dict().items():
                    response[name] = value
                return response
            response = self.get_response(request)
            headers = RateLimitHeaders.from_result(result)
            for name, value in headers.to_dict().items():
                response[name] = value
            return response

    return RateLimitMiddleware