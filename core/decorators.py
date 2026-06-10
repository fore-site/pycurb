import functools
from typing import Callable, Optional, Union, Any, cast
from .resolver import MutableRuleResolver
from .limiter import RateLimiter
from .limiter_sync import RateLimiterSync
from .models import LimitRule, RateLimitResult
from ..utils import parse_rate_limit_string

class RateLimitExceeded(Exception):
    def __init__(self, result: RateLimitResult):
        self.result = result
        super().__init__(f"Rate limit exceeded. Retry after {result.reset_at} seconds.")

def arg_extractor(*arg_names: str) -> Callable[..., str]:
    """
    Helper to create a key extractor that combines values of specified argument names.
    Arguments must be passed as keyword arguments; positional arguments are ignored.

    Example:
        @rate_limit(limiter, rule_name="api", key_extractor=arg_extractor("user_id", "tenant"))
        async def get_data(user_id: int, tenant: str):
            ...
    """
    def extractor(*args: Any, **kwargs: Any) -> str:
        parts = [str(kwargs.get(name, "")) for name in arg_names]
        # fallback if all parts empty
        if not any(parts):
            raise ValueError(f"None of the specified argument names {arg_names} were found in kwargs: {kwargs}")
        return ":".join(parts)
    return extractor

def rate_limit(
    limiter: Union[RateLimiter, RateLimiterSync],
    *,
    rule_name: Optional[str] = None,
    limit_str: Optional[str] = None,
    algorithm: str = "sliding_window",
    key_extractor: Optional[Callable[..., str]],
    raise_on_limit: bool = True,
):
    """
    Unified decorator for rate limiting (both async and sync).

    Args:
        limiter: RateLimiter (async) or RateLimiterSync (sync) instance.
        rule_name: Name of an existing rule in the limiter's resolver.
        limit_str: Shorthand string (e.g., "100/s") to create a new rule.
        algorithm: Algorithm to use when creating a rule from limit_str.
        key_extractor: Function extracting key (unique identifier) from function arguments.
        raise_on_limit: If True, raises RateLimitExceeded when limit exceeded.

    Exactly one of rule_name or limit_str must be provided.
    """
    if (rule_name is None) == (limit_str is None):
        raise ValueError("Provide exactly one of 'rule_name' or 'limit_str'")
    if key_extractor is None:
        raise TypeError("key_extractor is required to extract the key for rate limiting")

    def decorator(func: Callable) -> Callable:
        # Determine the effective rule name
        if rule_name is not None:
            effective_rule_name = rule_name
        else:
            # Create a new rule from shorthand
            effective_rule_name = f"{func.__module__}.{func.__qualname__}"
            limit, window = parse_rate_limit_string(limit_str)  # type: ignore
            rule = LimitRule(
                name=effective_rule_name,
                algorithm=algorithm,    # type: ignore[arg-type]
                limit=limit,
                window=window,
            )
            # Add to resolver (must be mutable)
            resolver = limiter.rule_resolver
            if not hasattr(resolver, 'add_rule'):
                raise TypeError(
                    "Limiter's rule resolver does not support dynamic rule addition. "
                    "Use MutableRuleResolver when using limit_str."
                )
            resolver = cast(MutableRuleResolver, resolver)
            resolver.add_rule(rule)

        # Wrap the function
        if isinstance(limiter, RateLimiter):
            # Async wrapper
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                key = key_extractor(*args, **kwargs)
                limiter_async = cast(RateLimiter, limiter)
                result = await limiter_async.check(key, effective_rule_name)
                if result.allowed:
                    return await func(*args, **kwargs)
                if raise_on_limit:
                    raise RateLimitExceeded(result)
                return None
            return async_wrapper
        else:
            # Sync wrapper
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                key = key_extractor(*args, **kwargs)
                limiter_sync = cast(RateLimiterSync, limiter)
                result = limiter_sync.check(key, effective_rule_name)
                if result.allowed:
                    return func(*args, **kwargs)
                if raise_on_limit:
                    raise RateLimitExceeded(result)
                return None
            return sync_wrapper
    return decorator