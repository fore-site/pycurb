import functools
import inspect
from typing import Callable, Optional, Union, Any, List, cast
from .limiter_async import AsyncRateLimiter
from .limiter import RateLimiter
from .models import LimitRule, RateLimitExceeded
from ..utils import parse_rate_limit_string


def is_async_limiter(limiter):
    return inspect.iscoroutinefunction(limiter.check)


def arg_extractor(*arg_names: str) -> Callable[..., str]:
    """
    Helper to create a key extractor that combines values of specified argument names.
    Arguments must be passed as keyword arguments; positional arguments are ignored.

    Example:
        ```python
        @rate_limit(limiter, rule_name="api", key_extractor=arg_extractor("user_id", "tenant"))
        async def get_data(user_id: int, tenant: str):
        ```
    """

    def extractor(*args: Any, **kwargs: Any) -> str:
        parts = [str(kwargs.get(name, "")) for name in arg_names]
        # fallback if all parts empty
        if not any(parts):
            raise ValueError(
                f"None of the specified argument names {arg_names} were found in kwargs: {kwargs}"
            )
        return ":".join(parts)

    return extractor


def rate_limit(
    limiter: Union[RateLimiter, AsyncRateLimiter],
    *,
    rule_name: Optional[Union[str, List[str]]] = None,
    limit_str: Optional[str] = None,
    algorithm: str = "sliding_window",
    key_extractor: Optional[Callable[..., str]],
):
    """
    Unified decorator for rate limiting (both async and sync).

    Args:
        limiter: RateLimiter (async) or RateLimiterSync (sync) instance.
        rule_name: Name of an existing rule in the limiter's resolver. Also accepts a list of names.
        limit_str: Shorthand string (e.g., "100/s") to create a new rule.
        algorithm: Algorithm to use when creating a rule from limit_str.
        key_extractor: Function extracting key (unique identifier) from function arguments.

    Raises:
        RateLimitExceeded: If rate limit has been exceeded.


    Exactly one of rule_name or limit_str must be provided.
    """
    if (rule_name is None) == (limit_str is None):
        raise ValueError("Provide exactly one of 'rule_name' or 'limit_str'")
    if key_extractor is None:
        raise TypeError("key_extractor must be provided")

    def decorator(func: Callable) -> Callable:
        func_is_async = inspect.iscoroutinefunction(func)
        limiter_is_async = inspect.iscoroutinefunction(limiter.check)

        # Validate consistency
        if func_is_async and not limiter_is_async:
            raise TypeError(
                "Async function requires an async RateLimiter (use RateLimiter, not RateLimiterSync)"
            )
        if not func_is_async and limiter_is_async:
            raise TypeError(
                "Sync function requires a sync RateLimiter (use RateLimiterSync, not RateLimiter)"
            )

        # Determine rule name and whether lazy creation is needed
        if rule_name is not None:
            effective_rule_name = rule_name
            need_rule_creation = False
        else:
            effective_rule_name = f"{func.__module__}.{func.__qualname__}"
            need_rule_creation = True
            _rule_created = False

        if func_is_async and limiter_is_async:
            limiter_async = cast(AsyncRateLimiter, limiter)

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> Callable:
                nonlocal _rule_created
                if need_rule_creation and not _rule_created:
                    # Parse shorthand inside the wrapper (only once)
                    limit, window = parse_rate_limit_string(limit_str)  # type: ignore
                    rule = LimitRule(
                        name=cast(str, effective_rule_name),
                        algorithm=algorithm,  # type: ignore
                        limit=limit,
                        window=window,
                    )
                    resolver = limiter_async.rule_resolver
                    if not hasattr(resolver, "add_rule"):
                        raise TypeError(
                            "Resolver instance must have 'add_rule' attribute when using 'limit_str' in decorator"
                        )

                    await resolver.add_rule(rule)  # type: ignore
                    _rule_created = True

                key = key_extractor(*args, **kwargs)
                result = await limiter_async.check(key, effective_rule_name)
                if result:
                    return await func(*args, **kwargs)
                else:
                    raise RateLimitExceeded(result)

            wrapper = async_wrapper
        else:
            limiter_sync = cast(RateLimiter, limiter)

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> Callable:
                nonlocal _rule_created
                if need_rule_creation and not _rule_created:
                    limit, window = parse_rate_limit_string(limit_str)  # type: ignore
                    rule = LimitRule(
                        name=cast(str, effective_rule_name),
                        algorithm=algorithm,  # type: ignore
                        limit=limit,
                        window=window,
                    )
                    resolver = limiter_sync.rule_resolver
                    if not hasattr(resolver, "add_rule"):
                        raise TypeError(
                            "Resolver class must have 'add_rule' attribute when using 'limit_str' in decorator"
                        )

                    resolver.add_rule(rule)  # type: ignore
                    _rule_created = True

                key = key_extractor(*args, **kwargs)
                result = limiter_sync.check(key, effective_rule_name)
                if result:
                    return func(*args, **kwargs)
                else:
                    raise RateLimitExceeded(result)

            wrapper = sync_wrapper
        return wrapper

    return decorator
