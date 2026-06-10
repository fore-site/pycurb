import functools
from typing import Callable
from .limiter import RateLimiter
from .limiter_sync import RateLimiterSync

from .models import RateLimitResult

class RateLimitExceeded(Exception):
    """Raised when a rate limit is exceeded."""
    def __init__(self, result: RateLimitResult):
        self.result = result
        super().__init__(f"Rate limit exceeded. Retry after {result.reset_at}")

def rate_limit(
    limiter: RateLimiter,
    rule_name: str,
    key_extractor: Callable[..., str] = lambda *args, **kwargs: "default",
    raise_on_limit: bool = True,
):
    """
    Decorator for async functions to apply rate limiting.

    Args:
        limiter: RateLimiter instance.
        rule_name: Name of the rule to apply.
        key_extractor: Function that extracts a key from the function arguments (args, kwargs).
        raise_on_limit: If True, raises RateLimitExceeded when limit exceeded; otherwise, the function is not called and returns None.

    Example:
        limiter = RateLimiter(storage, rules)
        @rate_limit(limiter, "api", key_extractor=lambda user_id, **kwargs: str(user_id))
        async def api_call(user_id: int):
            return "data"
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            key = key_extractor(*args, **kwargs)
            result = await limiter.check(key, rule_name)
            if result.allowed:
                return await func(*args, **kwargs)
            elif raise_on_limit:
                raise RateLimitExceeded(result)
            else:
                return None
        return wrapper
    return decorator


def rate_limit_sync(
    limiter: RateLimiterSync,
    rule_name: str,
    key_extractor: Callable[..., str] = lambda *args, **kwargs: "default",
    raise_on_limit: bool = True,
):
    """
    Decorator for sync functions to apply rate limiting.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = key_extractor(*args, **kwargs)
            result = limiter.check(key, rule_name)
            if result.allowed:
                return func(*args, **kwargs)
            elif raise_on_limit:
                raise RateLimitExceeded(result)
            else:
                return None
        return wrapper
    return decorator