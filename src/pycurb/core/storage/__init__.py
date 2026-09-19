"""
Storage backends for pycurb.

The Redis backends are re-exported here, but loaded lazily (PEP 562 module
``__getattr__``): importing this package must not require the optional
``redis`` dependency. The Redis modules themselves import ``redis`` at their
top level, so they are only loaded when ``RedisStorage`` /
``AsyncRedisStorage`` is actually accessed.

Accessing a Redis backend without ``redis`` installed raises an ImportError
with an actionable install hint, instead of the raw ModuleNotFoundError that
an eager import would produce at package import time.
"""

from typing import TYPE_CHECKING, Any

from .base import Storage
from .base_async import AsyncStorage
from .memory import MemoryStorage
from .memory_async import AsyncMemoryStorage

if TYPE_CHECKING:  # pragma: no cover - static analysis only
    from .redis import RedisStorage
    from .redis_async import AsyncRedisStorage

__all__ = [
    "Storage",
    "AsyncStorage",
    "AsyncMemoryStorage",
    "AsyncRedisStorage",
    "MemoryStorage",
    "RedisStorage",
]

_MISSING_REDIS_HINT = (
    "RedisStorage requires the optional 'redis' dependency. "
    "Install it with: pip install pycurb[redis]"
)


def __getattr__(name: str) -> Any:
    """Lazily load Redis backends (PEP 562)."""
    if name in ("RedisStorage", "AsyncRedisStorage"):
        try:
            import redis  # noqa: F401
        except ImportError as exc:
            raise ImportError(_MISSING_REDIS_HINT) from exc

        if name == "RedisStorage":
            from .redis import RedisStorage

            return RedisStorage

        from .redis_async import AsyncRedisStorage

        return AsyncRedisStorage

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
