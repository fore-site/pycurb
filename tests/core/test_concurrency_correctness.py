"""Correctness under concurrency: verify limiter semantics hold under load.

These tests submit many concurrent requests at one (or few) rate-limit
keys and assert the EXACT number of acceptances implied by each
algorithm's semantics. Exact counts are only assertable because every
storage path is atomic:

- sync memory: per-key threading.Lock around each check
- async memory: single-threaded event loop, no awaits inside a check
- sync/async redis: each check is one atomic Lua script

A lost update or duplicate allowance under contention would change the
accepted count, which is exactly what these tests detect.

Expected counts, per algorithm (fresh key, batch duration << window,
negligible refill/leak during the burst):

- sliding_window(limit=N, window=3600): every request within the window
  appends if len(queue) < N -> accepts exactly min(N, M).
- fixed_window(limit=N, window=3600): counter capped at N -> exactly
  min(N, M). window=3600 makes a minute-boundary crossing during the
  batch impossible, which would otherwise reset the count mid-burst.
  (A hour-boundary straddle would double the accepted count, but the
  burst lasts milliseconds, so the odds are ~1e-6 per run.)
- token_bucket(capacity=N, refill_rate=N/3600): starts with N tokens;
  the burst drains them. Refill during the batch is <= batch_seconds *
  N/3600 << 1 token, and the post-burst token level is ~0, so no extra
  acceptance can occur -> exactly min(N, M).
- leaky_bucket(capacity=N, leak_rate=N/3600): queue starts empty,
  accepts while queue < N; leak during the batch floors to 0 extra
  slots -> exactly min(N, M).
- gcra(capacity=N, rate=N/3600): burst tolerance is capacity-1 after
  the first packet (the tolerance condition scales with 1/rate on both
  sides, so the accepted count is rate-independent) -> exactly
  min(N, M).

These tests are deliberately NOT part of the performance benchmark:
per-request bookkeeping here would contaminate timing.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, List, Tuple

import pytest

from pycurb.core import (
    AsyncMemoryStorage,
    AsyncRateLimiter,
    LimitRule,
    MemoryStorage,
    RateLimiter,
)

from tests.conftest import is_redis_available

M = 250  # concurrent requests per burst
N = 10  # limit / capacity
WINDOW = 3600

if is_redis_available():
    import redis
    import redis.asyncio as aioredis

    from pycurb.core.storage.redis import RedisStorage
    from pycurb.core.storage.redis_async import AsyncRedisStorage


def make_rule(algorithm: str) -> LimitRule:
    """Equivalent-capacity rules; drain rates are tiny so the burst
    determines the outcome, not refill during the batch."""
    base = dict(name="ctest", algorithm=algorithm)
    if algorithm == "sliding_window":
        return LimitRule(limit=N, window=WINDOW, **base)
    if algorithm == "fixed_window":
        return LimitRule(limit=N, window=WINDOW, **base)
    if algorithm == "token_bucket":
        return LimitRule(capacity=N, refill_rate=N / WINDOW, **base)
    if algorithm == "leaky_bucket":
        return LimitRule(capacity=N, leak_rate=N / WINDOW, **base)
    if algorithm == "gcra":
        return LimitRule(capacity=N, refill_rate=N / WINDOW, **base)
    raise ValueError(algorithm)


ALGORITHMS = [
    "sliding_window",
    "fixed_window",
    "token_bucket",
    "leaky_bucket",
    "gcra",
]


def burst_sync(limiter: RateLimiter, key: str, m: int) -> List[bool]:
    """Fire m requests at one key from m threads, released simultaneously."""
    return [r[0] for r in burst_sync_full(limiter, key, m)]


def burst_sync_full(
    limiter: RateLimiter, key: str, m: int
) -> List[Tuple[bool, int, float]]:
    """burst_sync variant returning full (allowed, remaining, reset_at)."""
    barrier = threading.Barrier(m)
    results: List[Tuple[bool, int, float]] = [(False, 0, 0.0)] * m
    start = threading.Event()

    def worker(i: int) -> None:
        start.wait()
        barrier.wait()
        result = limiter.check(key, "ctest")
        results[i] = (result.allowed, result.remaining, result.reset_at)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(m)]
    for t in threads:
        t.start()
    start.set()
    for t in threads:
        t.join()
    return results


async def burst_async(limiter: AsyncRateLimiter, key: str, m: int) -> List[bool]:
    """Fire m requests at one key as gathered tasks on one event loop."""

    async def worker() -> bool:
        result = await limiter.check(key, "ctest")
        return result.allowed

    return list(await asyncio.gather(*(worker() for _ in range(m))))


def assert_burst_semantics(
    algorithm: str, allowed: List[bool], denied_followups: List[bool]
) -> None:
    accepted = sum(allowed)
    assert accepted == min(N, M), (
        f"{algorithm}: expected exactly {min(N, M)} acceptances, got {accepted} "
        f"(lost update or duplicate allowance under contention)"
    )
    # The deny path must deny: immediate follow-ups cannot be allowed,
    # because refill/leak during the burst window is negligible.
    assert not any(denied_followups), (
        f"{algorithm}: follow-up requests after exhaustion were allowed: "
        f"{denied_followups}"
    )


def followup_sync(limiter: RateLimiter, key: str, count: int = 5) -> List[bool]:
    return [limiter.check(key, "ctest").allowed for _ in range(count)]


# ---------------------------------------------------------------------------
# sync memory
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_sync_memory_exact_acceptance_under_contention(algorithm):
    rule = make_rule(algorithm)
    limiter = RateLimiter(MemoryStorage(), [rule])
    key = f"ctest_sync_mem_{algorithm}_{time.time_ns()}"

    allowed = burst_sync(limiter, key, M)
    followups = followup_sync(limiter, key)
    assert_burst_semantics(algorithm, allowed, followups)


def test_sync_memory_key_isolation_under_concurrency():
    """Concurrent traffic on many distinct keys must not interfere."""
    limiter = RateLimiter(MemoryStorage(), [make_rule("sliding_window")])
    keys = [f"ctest_iso_{i}_{time.time_ns()}" for i in range(100)]
    per_key = 5  # below N, so every request must be allowed

    all_results: List[bool] = []
    threads: List[threading.Thread] = []
    results_lock = threading.Lock()

    def hammer(k: str) -> None:
        local = burst_sync(limiter, k, per_key)
        with results_lock:
            all_results.extend(local)

    for k in keys:
        t = threading.Thread(target=hammer, args=(k,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    assert all(all_results), (
        f"requests on independent keys were incorrectly denied "
        f"({sum(1 for r in all_results if not r)}/{len(all_results)} denied)"
    )


# ---------------------------------------------------------------------------
# async memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("algorithm", ALGORITHMS)
async def test_async_memory_exact_acceptance_under_contention(algorithm):
    rule = make_rule(algorithm)
    limiter = AsyncRateLimiter(AsyncMemoryStorage(), [rule])
    key = f"ctest_async_mem_{algorithm}_{time.time_ns()}"

    allowed = await burst_async(limiter, key, M)
    followups = [await limiter.check(key, "ctest") for _ in range(5)]
    assert_burst_semantics(algorithm, allowed, [f.allowed for f in followups])


# ---------------------------------------------------------------------------
# redis (sync + async) — exercises real Lua-script atomicity over the wire
# ---------------------------------------------------------------------------

REDIS_VARIANTS = ["sync_redis", "async_redis"]

# One client (and pool) per variant for the whole module: each burst needs
# up to M concurrent connections, and creating a fresh client per test
# accumulates hundreds of connections server-side until the server or the
# fd limit rejects new ones ("Too many connections" -> fail-closed denials).
# A shared pool of M+headroom is reused across tests instead.
_max_connections = M + 50
_sync_client: Any = None


def _redis_client(variant: str) -> Any:
    if variant == "sync_redis":
        global _sync_client
        if _sync_client is None:
            _sync_client = redis.Redis(
                host="localhost",
                port=6379,
                decode_responses=True,
                max_connections=_max_connections,
            )
        return _sync_client
    # Async clients are NOT shared across tests: asyncio.run() creates a
    # fresh event loop per call, and pooled connections are bound to the
    # loop they were created on (reusing them on another loop raises
    # "Event loop is closed"). Each async scenario builds and closes its
    # own pool, which releases the connections immediately.
    return aioredis.Redis(
        host="localhost",
        port=6379,
        decode_responses=True,
        max_connections=_max_connections,
    )


@pytest.fixture(scope="session", autouse=True)
def _manage_redis_clients():
    yield
    global _sync_client
    # Best-effort cleanup of any leftover ctest: keys.
    if _sync_client is not None:
        try:
            keys = list(_sync_client.scan_iter(match="ctest:*"))
            if keys:
                _sync_client.delete(*keys)
        except Exception:
            pass
        _sync_client.close()
        _sync_client = None


@pytest.mark.parametrize("algorithm", ALGORITHMS)
@pytest.mark.parametrize("variant", REDIS_VARIANTS)
def test_redis_exact_acceptance_under_contention(algorithm, variant):
    if not is_redis_available():
        pytest.skip("Redis not available")

    rule = make_rule(algorithm)
    key = f"ctest_{variant}_{algorithm}_{time.time_ns()}"
    is_async = variant == "async_redis"

    if is_async:

        async def scenario() -> Tuple[List[bool], List[bool]]:
            client = _redis_client(variant)
            limiter = AsyncRateLimiter(
                AsyncRedisStorage(client, key_prefix="ctest:"), [rule]
            )
            allowed = await burst_async(limiter, key, M)
            followups = [(await limiter.check(key, "ctest")).allowed for _ in range(5)]
            await client.delete("ctest:" + key)
            return allowed, followups

        allowed, followups = asyncio.run(scenario())
    else:
        client = _redis_client(variant)
        limiter = RateLimiter(RedisStorage(client, key_prefix="ctest:"), [rule])
        allowed = burst_sync(limiter, key, M)
        followups = followup_sync(limiter, key)
        client.delete("ctest:" + key)

    assert_burst_semantics(algorithm, allowed, followups)


# ---------------------------------------------------------------------------
# clock-regression robustness (regression test for the floor(-eps) fix)
# ---------------------------------------------------------------------------


def _make_storage(variant: str) -> Any:
    if variant == "sync_memory":
        return MemoryStorage()
    if variant == "sync_redis":
        return RedisStorage(
            _redis_client("sync_redis"), key_prefix="ctest:", use_redis_time=False
        )
    raise ValueError(variant)


VARIANTS = ["sync_memory", "sync_redis"]


@pytest.mark.parametrize("variant", VARIANTS)
def test_leaky_bucket_clock_regression_does_not_inflate_queue(variant):
    """A request timestamped slightly in the past must not grow the queue.

    Before the clamp fix, floor(negative_elapsed * rate) == -1 and each
    regressed call silently added a phantom queue slot.

    Behavioral formulation (no peeking at backend internals): with
    capacity 3 the first three arrivals must all be accepted and the
    fourth denied. With the bug, the regressed arrival adds a phantom
    slot, the queue reads full after two real arrivals, and the third
    arrival is wrongly denied.
    """
    if variant == "sync_redis" and not is_redis_available():
        pytest.skip("Redis not available")
    storage = _make_storage(variant)
    key = f"ctest_regress_leaky_{variant}_{time.time_ns()}"
    rate = 10 / WINDOW  # negligible leak over the test's microsecond span

    a1, _, _ = storage.leaky_bucket(key, capacity=3, leak_rate=rate, now=1000.0)
    a2, _, _ = storage.leaky_bucket(key, capacity=3, leak_rate=rate, now=999.9999)
    a3, _, _ = storage.leaky_bucket(key, capacity=3, leak_rate=rate, now=1000.1)
    a4, _, _ = storage.leaky_bucket(key, capacity=3, leak_rate=rate, now=1000.2)

    assert (a1, a2, a3) == (True, True, True), (
        f"clock regression inflated the queue: accepted={a1, a2, a3}"
    )
    assert a4 is False, "capacity=3 accepted a fourth arrival (state inconsistent)"


@pytest.mark.parametrize("variant", VARIANTS)
def test_token_bucket_clock_regression_does_not_wrongly_deny(variant):
    """A regressed timestamp must not drain tokens into wrongful denial."""
    if variant == "sync_redis" and not is_redis_available():
        pytest.skip("Redis not available")
    storage = _make_storage(variant)
    key = f"ctest_regress_token_{variant}_{time.time_ns()}"

    # Fresh bucket: 10 tokens. Consume one at t=1000 -> 9 remain
    # (remaining is the post-consumption count in both backends).
    allowed, remaining, _ = storage.token_bucket(key, 10, 10.0, 1000.0)
    assert allowed, "fresh bucket wrongly denied"
    assert remaining == 9, f"expected 9 after first consume, got {remaining}"

    # A request timestamped 50s in the past (bad clock / out-of-order
    # client). Unclamped, elapsed=-50 * rate=10 would subtract 500 tokens
    # and wrongly deny; clamped, the bucket is untouched: consume one
    # more, 8 remain.
    allowed, remaining, _ = storage.token_bucket(key, 10, 10.0, 950.0)
    assert allowed, "clock regression wrongly denied a request"
    assert remaining == 8, f"tokens disturbed by regression: remaining={remaining}"


def test_redis_key_isolation_under_concurrency():
    """Many keys, concurrent bursts: per-key counts must be independent."""
    if not is_redis_available():
        pytest.skip("Redis not available")

    limiter = RateLimiter(
        RedisStorage(_redis_client("sync_redis"), key_prefix="ctest:"),
        [make_rule("sliding_window")],
    )
    storage = limiter.storage
    keys = [f"ctest_iso_{i}_{time.time_ns()}" for i in range(50)]
    per_key = 5

    # A transient Redis failure produces a fail-closed denial with the
    # fingerprint (False, 0, inf). That is correct limiter behavior but
    # NOT a cross-key isolation violation, so results are classified:
    # only semantic denials fail this test.
    results: List[Tuple[bool, int, float]] = []
    results_lock = threading.Lock()

    def hammer(k: str) -> None:
        local = burst_sync_full(limiter, k, per_key)
        with results_lock:
            results.extend(local)

    threads = []
    for k in keys:
        t = threading.Thread(target=hammer, args=(k,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    storage.redis.delete(*["ctest:" + k for k in keys])

    semantic_denials = [
        r for r in results if not r[0] and not (r[1] == 0 and r[2] == float("inf"))
    ]
    fail_closed = sum(1 for r in results if not r[0] and r[2] == float("inf"))
    assert not semantic_denials, (
        f"Redis: requests on independent keys were incorrectly denied "
        f"({len(semantic_denials)}/{len(results)} denied): {semantic_denials[:5]}"
    )
    if fail_closed:
        print(
            f"note: {fail_closed}/{len(results)} requests hit fail-closed "
            f"(transient Redis unavailability), not counted as violations"
        )
