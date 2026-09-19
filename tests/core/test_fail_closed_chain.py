"""
Regression tests for the Redis failure (fail-open / fail-closed) chain.

When Redis is unavailable and no fallback storage is configured, storage
returns `reset_at = float("inf")` — an honest "reset time unknown" signal.
These tests assert that the *entire* downstream chain (algorithm -> limiter ->
models -> adapters) handles that signal without raising OverflowError.

Before the fix, `math.ceil(inf)` / `int(inf)` crashed limiter.check(),
RateLimitHeaders.from_result(), RateLimitExceeded, and the FastAPI
dependency — i.e. the safety net itself was broken.
"""

import math

import pytest
import redis.exceptions

from pycurb.core.limiter import RateLimiter
from pycurb.core.limiter_async import AsyncRateLimiter
from pycurb.core.models import LimitRule, RateLimitHeaders, RateLimitResult
from pycurb.core.storage.redis import RedisStorage
from pycurb.core.storage.redis_async import AsyncRedisStorage


class FailingRedisClient:
    """Any attribute access returns a callable that raises a redis error."""

    def __getattr__(self, name):
        def failing(*args, **kwargs):
            raise redis.exceptions.ConnectionError(
                f"Simulated Redis failure for {name}"
            )

        return failing


def make_sync_limiter(fail_open: bool) -> RateLimiter:
    storage = RedisStorage(
        FailingRedisClient(), fail_open=fail_open, use_redis_time=False
    )
    rule = LimitRule(name="api", algorithm="sliding_window", limit=5, window=10)
    return RateLimiter(storage, [rule])


def make_async_limiter(fail_open: bool) -> AsyncRateLimiter:
    storage = AsyncRedisStorage(
        FailingRedisClient(), fail_open=fail_open, use_redis_time=False
    )
    rule = LimitRule(name="api", algorithm="sliding_window", limit=5, window=10)
    return AsyncRateLimiter(storage, [rule])


# ---------------------------------------------------------------------------
# Sync limiter end-to-end (this used to crash inside the algorithm layer)
# ---------------------------------------------------------------------------


def test_fail_closed_limiter_check_does_not_crash_sync():
    limiter = make_sync_limiter(fail_open=False)
    result = limiter.check("k", "api")
    assert result.allowed is False
    assert result.remaining == 0
    assert math.isinf(result.reset_at)
    assert result.retry_after is None


def test_fail_open_limiter_check_does_not_crash_sync():
    limiter = make_sync_limiter(fail_open=True)
    result = limiter.check("k", "api")
    assert result.allowed is True
    assert result.retry_after is None


# ---------------------------------------------------------------------------
# Async limiter end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fail_closed_limiter_check_does_not_crash_async():
    limiter = make_async_limiter(fail_open=False)
    result = await limiter.check("k", "api")
    assert result.allowed is False
    assert result.remaining == 0
    assert math.isinf(result.reset_at)
    assert result.retry_after is None


@pytest.mark.asyncio
async def test_fail_open_limiter_check_does_not_crash_async():
    limiter = make_async_limiter(fail_open=True)
    result = await limiter.check("k", "api")
    assert result.allowed is True
    assert result.retry_after is None


# ---------------------------------------------------------------------------
# models layer
# ---------------------------------------------------------------------------


def test_headers_from_result_with_infinite_reset_at():
    result = RateLimitResult(
        allowed=False, remaining=0, reset_at=float("inf"), limit=10
    )
    headers = RateLimitHeaders.from_result(result)
    assert headers.reset is None
    assert headers.retry_after is None
    # Unknown values must be omitted, not sent as bogus strings.
    d = headers.to_dict()
    assert d["X-RateLimit-Limit"] == "10"
    assert d["X-RateLimit-Remaining"] == "0"
    assert "X-RateLimit-Reset" not in d
    assert "Retry-After" not in d


def test_headers_from_result_finite_reset_at_unchanged():
    result = RateLimitResult(allowed=False, remaining=0, reset_at=1000.0, limit=10)
    headers = RateLimitHeaders.from_result(result, now=950)
    assert headers.reset == 1000
    assert headers.retry_after == 50


# ---------------------------------------------------------------------------
# Adapter layer
# ---------------------------------------------------------------------------


def make_fake_request() -> object:
    """Minimal request stand-in: extractors only touch .headers/.client/.state."""
    request = type("R", (), {})()
    request.headers = {}  # type: ignore[attr-defined]
    request.client = None  # type: ignore[attr-defined]
    request.state = type("S", (), {})()  # type: ignore[attr-defined]
    return request


def test_fastapi_dependency_fail_closed_no_retry_after():
    """The FastAPI dependency must not crash on int(inf) with fail-closed."""
    import asyncio

    from fastapi import HTTPException

    from pycurb.adapters.fastapi.dependencies import rate_limiter

    limiter = make_async_limiter(fail_open=False)
    dependency = rate_limiter(limiter, "api")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(dependency(make_fake_request()))

    assert exc_info.value.status_code == 429
    # Reset time unknown -> no Retry-After header (previously OverflowError)
    assert not (exc_info.value.headers or {}).get("Retry-After")


def test_fastapi_dependency_fail_closed_finite_reset_sets_retry_after():
    """Finite reset_at must still produce Retry-After (regression guard)."""
    import asyncio
    import time

    from fastapi import HTTPException

    from pycurb.adapters.fastapi.dependencies import rate_limiter

    class DenyLimiter:
        check_calls = 0

        async def check(self, key, rule_names):
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=time.time() + 7,
                limit=10,
            )

    dependency = rate_limiter(DenyLimiter(), "api")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(dependency(make_fake_request()))

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers is not None
    assert int(exc_info.value.headers["Retry-After"]) >= 1
