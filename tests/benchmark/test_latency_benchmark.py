import pytest
import asyncio
import time
import os
import json
import statistics
import redis
import redis.asyncio as aioredis
from pycurb.core import (
    RateLimiter,
    AsyncRateLimiter,
    MemoryStorage,
    AsyncMemoryStorage,
    LimitRule,
)
from pycurb.core.storage.redis import RedisStorage
from pycurb.core.storage.redis_async import AsyncRedisStorage


_sync_redis_pool = None
_async_redis_pool = None
LATENCY_RESULTS = []

# Create a single event loop for the test suite
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


@pytest.fixture(scope="session", autouse=True)
def cleanup_redis_pools():
    yield
    # After all tests, close the pools
    global _async_redis_pool, _sync_redis_pool
    if "_async_redis_pool" in globals() and _async_redis_pool:
        loop.run_until_complete(_async_redis_pool.disconnect())
    if "_sync_redis_pool" in globals() and _sync_redis_pool:
        _sync_redis_pool.disconnect()
    # write aggregated latency results to docs/data/latency.json
    try:
        out_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "docs", "data")
        )
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, "latency.json")
        with open(out_file, "w") as fh:
            json.dump(LATENCY_RESULTS, fh)
    except Exception:
        pass
    loop.close()


# Helpers
def is_redis_available():
    try:
        r = redis.Redis(host="localhost", port=6379)
        return r.ping()
    except:
        return False


def get_sync_redis_pool():
    global _sync_redis_pool
    if _sync_redis_pool is None:
        _sync_redis_pool = redis.ConnectionPool(
            host="localhost",
            port=6379,
            max_connections=CONCURRENCY + 10,
            decode_responses=True,
        )
    return _sync_redis_pool


def get_async_redis_pool():
    global _async_redis_pool
    if _async_redis_pool is None:
        _async_redis_pool = aioredis.ConnectionPool(
            host="localhost",
            port=6379,
            max_connections=CONCURRENCY + 10,
            decode_responses=True,
        )
    return _async_redis_pool


def create_rule(algorithm, limit):
    """Create a LimitRule for the given algorithm and limit."""
    if algorithm in ("sliding_window", "fixed_window"):
        return LimitRule(name="bench", algorithm=algorithm, limit=limit, window=60)
    elif algorithm == "token_bucket":
        return LimitRule(
            name="bench",
            algorithm="token_bucket",
            capacity=limit,
            refill_rate=limit / 60,
        )
    elif algorithm == "leaky_bucket":
        return LimitRule(
            name="bench", algorithm="leaky_bucket", capacity=limit, leak_rate=limit / 60
        )
    elif algorithm == "gcra":
        return LimitRule(
            name="bench", algorithm="gcra", capacity=limit, refill_rate=limit / 60
        )
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")


def create_storage(storage_type):
    """Create a storage instance and its corresponding limiter class."""
    if storage_type == "async_memory":
        return AsyncMemoryStorage(), AsyncRateLimiter, True
    elif storage_type == "sync_memory":
        return MemoryStorage(), RateLimiter, False
    elif storage_type == "async_redis":
        pool = get_async_redis_pool()
        client = aioredis.Redis(connection_pool=pool)
        return AsyncRedisStorage(client, key_prefix="bench:"), AsyncRateLimiter, True
    elif storage_type == "sync_redis":
        pool = get_sync_redis_pool()
        client = redis.Redis(connection_pool=pool)
        return RedisStorage(client, key_prefix="bench:"), RateLimiter, False
    else:
        raise ValueError(f"Unknown storage type: {storage_type}")


async def prefill_limiter(limiter, key, rule_name, target):
    """Send `target` requests to reach fill level."""
    if target <= 0:
        return
    for _ in range(target):
        await limiter.check(key, rule_name)


def prefill_limiter_sync(limiter, key, rule_name, target):
    if target <= 0:
        return
    for _ in range(target):
        limiter.check(key, rule_name)


async def async_delete_redis_key(storage, key):
    """Delete the Redis key for async storage."""
    if hasattr(storage, "redis") and hasattr(storage.redis, "delete"):
        await storage.redis.delete(key)


def sync_delete_redis_key(storage, key):
    """Delete the Redis key for sync storage."""
    if hasattr(storage, "redis") and hasattr(storage.redis, "delete"):
        storage.redis.delete(key)


# Benchmark Configuration
ALGORITHMS = ["sliding_window", "fixed_window", "token_bucket", "leaky_bucket", "gcra"]
STORAGE_TYPES = ["async_memory", "sync_memory"]
if is_redis_available():
    STORAGE_TYPES.extend(["async_redis", "sync_redis"])
CONCURRENCY = 100
TOTAL_REQUESTS = 1000
NUM_USERS = 100
LIMIT_VALUES = [100, 500, 1000]
FILL_LEVELS = [0.0, 0.5, 0.95]
LATENCY_ITERATIONS = 1000
LATENCY_ROUNDS = 5


# Benchmark Test
@pytest.mark.benchmark
@pytest.mark.parametrize("algorithm", ALGORITHMS)
@pytest.mark.parametrize("storage_type", STORAGE_TYPES)
@pytest.mark.parametrize("limit", LIMIT_VALUES)
@pytest.mark.parametrize("fill_level", FILL_LEVELS)
def test_rate_limit_benchmark(benchmark, algorithm, storage_type, limit, fill_level):
    """
    Benchmark a batch of rate limit checks.

    Dimensions:
        - algorithm
        - storage backend (memory/redis, async/sync)
        - rate limit (limit value)
        - fill level (percentage of limit already consumed)
    """
    if "redis" in storage_type and not is_redis_available():
        pytest.skip("Redis not available")

    storage, limiter_class, is_async = create_storage(storage_type)
    rule = create_rule(algorithm, limit)
    limiter = limiter_class(storage, [rule])

    # Key for each virtual user
    keys = [f"vu_{i}_{algorithm}_{storage_type}" for i in range(NUM_USERS)]
    rule_name = "bench"

    # Prefill to fill_level
    target = int(limit * fill_level)

    if is_async:
        for key in keys:
            loop.run_until_complete(prefill_limiter(limiter, key, rule_name, target))
    else:
        for key in keys:
            prefill_limiter_sync(limiter, key, rule_name, target)

    # Measure per-operation latency: one limiter.check() per pedantic iteration.
    # Warmup a single call first.
    if is_async:
        loop.run_until_complete(limiter.check(keys[0], rule_name))

        latencies = []

        def bench_call():
            k = keys[int(time.time_ns()) % NUM_USERS]
            t0 = time.perf_counter()
            res = loop.run_until_complete(limiter.check(k, rule_name))
            t1 = time.perf_counter()
            latencies.append(t1 - t0)
            return res

        result = benchmark.pedantic(
            bench_call, iterations=LATENCY_ITERATIONS, rounds=LATENCY_ROUNDS
        )
    else:
        limiter.check(keys[0], rule_name)

        latencies = []

        def bench_call_sync():
            k = keys[int(time.time_ns()) % NUM_USERS]
            t0 = time.perf_counter()
            res = limiter.check(k, rule_name)
            t1 = time.perf_counter()
            latencies.append(t1 - t0)
            return res

        result = benchmark.pedantic(
            bench_call_sync, iterations=LATENCY_ITERATIONS, rounds=LATENCY_ROUNDS
        )

    # Prepare and write latency summary JSON
    try:
        if latencies:
            samples = sorted(latencies)
            total = len(samples)
            mean = statistics.mean(samples)
            median = statistics.median(samples)
            stdev = statistics.stdev(samples) if total > 1 else 0.0
            p95 = samples[int(0.95 * (total - 1))]
            p99 = samples[int(0.99 * (total - 1))]
            summary = {
                "metric": "latency",
                "algorithm": algorithm,
                "storage": storage_type,
                "limit": limit,
                "fill_level": fill_level,
                "iterations": LATENCY_ITERATIONS,
                "rounds": LATENCY_ROUNDS,
                "samples": total,
                "mean_s": mean,
                "median_s": median,
                "p95_s": p95,
                "p99_s": p99,
                "min_s": samples[0],
                "max_s": samples[-1],
                "stdev_s": stdev,
                "timestamp": int(time.time()),
            }
            LATENCY_RESULTS.append(summary)
    except Exception:
        pass

    # Clean up Redis keys if needed
    if "redis" in storage_type:
        if is_async:
            for key in keys:
                loop.run_until_complete(async_delete_redis_key(storage, key))
        else:
            for key in keys:
                sync_delete_redis_key(storage, key)
