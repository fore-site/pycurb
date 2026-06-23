import functools
import inspect
from typing import Union, List, Callable, Optional, cast
from django.http import JsonResponse, HttpRequest
from pycurb.core import RateLimiter, AsyncRateLimiter
from pycurb.core.models import RateLimitHeaders
from .extractors import ip_extractor


def rate_limit(
    limiter: Union[RateLimiter, AsyncRateLimiter],
    rule_name: Union[str, List[str]],
    key_extractor: Callable[[HttpRequest], str] = ip_extractor,
    on_limit: Optional[Callable] = None,
):
    """
    Django view decorator for rate limiting.
    Works for sync and async views.
    Returns 429 JSON response when limit exceeded.
    """

    def decorator(view_func):
        is_async = inspect.iscoroutinefunction(view_func)
        limiter_is_async = isinstance(limiter, AsyncRateLimiter)  # RateLimiter is async

        if is_async and not limiter_is_async:
            raise TypeError(
                "Async view requires an async RateLimiter (use AsyncRateLimiter, not RateLimiter)"
            )
        if not is_async and limiter_is_async:
            raise TypeError(
                "Sync view requires a sync RateLimiter (use RateLimiter, not AsyncRateLimiter)"
            )

        @functools.wraps(view_func)
        def sync_wrapper(request, *args, **kwargs):
            key = key_extractor(request)
            limiter_sync = cast(RateLimiter, limiter)
            if not (result:= limiter_sync.check(key, rule_name)):
                if on_limit:
                    return on_limit(request, result)
                headers = RateLimitHeaders.from_result(result)
                response = JsonResponse({"detail": "Rate limit exceeded"}, status=429)
                for name, value in headers.to_dict().items():
                    response[name] = value
                return response

            response = view_func(request, *args, **kwargs)
            headers = RateLimitHeaders.from_result(result)
            for name, value in headers.to_dict().items():
                response[name] = value
            return response

        @functools.wraps(view_func)
        async def async_wrapper(request, *args, **kwargs):
            key = key_extractor(request)
            limiter_async = cast(AsyncRateLimiter, limiter)
            if not (result:= await limiter_async.check(key, rule_name)):
                if on_limit:
                    return on_limit(request, result)
                headers = RateLimitHeaders.from_result(result)
                response = JsonResponse({"detail": "Rate limit exceeded"}, status=429)
                for name, value in headers.to_dict().items():
                    response[name] = value
                return response

            response = await view_func(request, *args, **kwargs)
            headers = RateLimitHeaders.from_result(result)
            for name, value in headers.to_dict().items():
                response[name] = value
            return response

        return async_wrapper if is_async else sync_wrapper

    return decorator
