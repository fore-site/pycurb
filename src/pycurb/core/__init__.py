"""
PyCurb core: models, limiters, resolvers, decorators, and storage backends.

Redis storage classes are re-exported but loaded lazily (PEP 562), so that
``import pycurb.core`` works without the optional ``redis`` dependency
installed. See ``pycurb.core.storage`` for details.
"""

from typing import TYPE_CHECKING, Any

from .models import LimitRule, RateLimitResult, RateLimitHeaders, RateLimitExceeded
from .limiter import RateLimiter
from .limiter_async import AsyncRateLimiter
from .resolver import RuleResolver, AsyncRuleResolver
from .decorators import rate_limit, arg_extractor
from .storage import MemoryStorage, AsyncMemoryStorage

if TYPE_CHECKING:  # pragma: no cover - static analysis only
    from .storage import RedisStorage, AsyncRedisStorage

__all__ = [
    "LimitRule",
    "RateLimitResult",
    "RateLimitHeaders",
    "RateLimiter",
    "AsyncRateLimiter",
    "RuleResolver",
    "AsyncRuleResolver",
    "MemoryStorage",
    "AsyncMemoryStorage",
    "RedisStorage",
    "AsyncRedisStorage",
    "rate_limit",
    "RateLimitExceeded",
    "arg_extractor",
]


def __getattr__(name: str) -> Any:
    """Lazily expose Redis storage backends without requiring redis (PEP 562)."""
    if name in ("RedisStorage", "AsyncRedisStorage"):
        from . import storage

        return getattr(storage, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
