import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import Any, List, Optional, Union, cast

from django.http import HttpRequest, JsonResponse
from django.http.response import HttpResponseBase

from pycurb.core import AsyncRateLimiter, RateLimiter
from pycurb.core.models import RateLimitHeaders, RateLimitResult

from .extractors import ip_extractor

SyncView = Callable[..., HttpResponseBase]
AsyncView = Callable[..., Awaitable[HttpResponseBase]]
View = Union[SyncView, AsyncView]
LimitCallback = Callable[[HttpRequest, RateLimitResult], Optional[HttpResponseBase]]


def rate_limit(
    limiter: Union[RateLimiter, AsyncRateLimiter],
    rule_name: Union[str, List[str]],
    key_extractor: Callable[[HttpRequest], str] = ip_extractor,
    on_limit: Optional[LimitCallback] = None,
) -> Callable[[View], View]:
    """
    Django view decorator for rate limiting.
    Works for sync and async views.
    Returns 429 for quota exhaustion and 503 when the storage backend is
    unavailable.
    """

    def with_headers(
        response: HttpResponseBase, result: RateLimitResult
    ) -> HttpResponseBase:
        for name, value in RateLimitHeaders.from_result(result).to_dict().items():
            response[name] = value
        return response

    def default_limit_response(result: RateLimitResult) -> JsonResponse:
        status_code = 503 if result.storage_unavailable else 429
        detail = (
            "Rate limiter unavailable"
            if result.storage_unavailable
            else "Rate limit exceeded"
        )
        return JsonResponse({"detail": detail}, status=status_code)

    def decorator(view_func: View) -> View:
        is_async = inspect.iscoroutinefunction(view_func)
        limiter_is_async = isinstance(limiter, AsyncRateLimiter)

        if is_async and not limiter_is_async:
            raise TypeError(
                "Async view requires an async RateLimiter (use AsyncRateLimiter, not RateLimiter)"
            )
        if not is_async and limiter_is_async:
            raise TypeError(
                "Sync view requires a sync RateLimiter (use RateLimiter, not AsyncRateLimiter)"
            )

        @functools.wraps(view_func)
        def sync_wrapper(
            request: HttpRequest, *args: Any, **kwargs: Any
        ) -> HttpResponseBase:
            key = key_extractor(request)
            limiter_sync = cast(RateLimiter, limiter)
            sync_view = cast(SyncView, view_func)
            if not (result := limiter_sync.check(key, rule_name)):
                response = (
                    on_limit(request, result)
                    if on_limit and not result.storage_unavailable
                    else None
                )
                if response is None:
                    response = default_limit_response(result)
                return with_headers(response, result)

            response = sync_view(request, *args, **kwargs)
            return with_headers(response, result)

        @functools.wraps(view_func)
        async def async_wrapper(
            request: HttpRequest, *args: Any, **kwargs: Any
        ) -> HttpResponseBase:
            key = key_extractor(request)
            limiter_async = cast(AsyncRateLimiter, limiter)
            async_view = cast(AsyncView, view_func)
            if not (result := await limiter_async.check(key, rule_name)):
                response = (
                    on_limit(request, result)
                    if on_limit and not result.storage_unavailable
                    else None
                )
                if response is None:
                    response = default_limit_response(result)
                return with_headers(response, result)

            response = await async_view(request, *args, **kwargs)
            return with_headers(response, result)

        return async_wrapper if is_async else sync_wrapper

    return decorator
