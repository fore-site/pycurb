import pytest
import asyncio
import concurrent.futures
import time
import redis
import redis.asyncio as aioredis
from pycurb.core import (
    RateLimiter, AsyncRateLimiter,
    MemoryStorage, AsyncMemoryStorage,
    LimitRule,
)
from pycurb.core.storage.redis import RedisStorage
from pycurb.core.storage.redis_async import AsyncRedisStorage


_sync_redis_pool = None
_async_redis_pool = None

# Create a single event loop for the test suite
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

@pytest.fixture(scope="session", autouse=True)
def cleanup_redis_pools():
    yield
    # After all tests, close the pools
    global _async_redis_pool, _sync_redis_pool
    if '_async_redis_pool' in globals() and _async_redis_pool:
        loop.run_until_complete(_async_redis_pool.disconnect())
    if '_sync_redis_pool' in globals() and _sync_redis_pool:
        _sync_redis_pool.disconnect()
    loop.close()

# Helpers
def is_redis_available():
    try:
        r = redis.Redis(host='localhost', port=6379)
        return r.ping()
    except:
        return False

def get_sync_redis_pool():
    global _sync_redis_pool
    if _sync_redis_pool is None:
        _sync_redis_pool = redis.ConnectionPool(
            host='localhost',
            port=6379,
            max_connections=CONCURRENCY + 10,
            decode_responses=True,
        )
    return _sync_redis_pool

def get_async_redis_pool():
    global _async_redis_pool
    if _async_redis_pool is None:
        _async_redis_pool = aioredis.ConnectionPool(
            host='localhost',
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
        return LimitRule(name="bench", algorithm="token_bucket", capacity=limit, refill_rate=limit/60)
    elif algorithm == "leaky_bucket":
        return LimitRule(name="bench", algorithm="leaky_bucket", capacity=limit, leak_rate=limit/60)
    elif algorithm == "gcra":
        return LimitRule(name="bench", algorithm="gcra", capacity=limit, refill_rate=limit/60)
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
    if hasattr(storage, 'redis') and hasattr(storage.redis, 'delete'):
        await storage.redis.delete(key)

def sync_delete_redis_key(storage, key):
    """Delete the Redis key for sync storage."""
    if hasattr(storage, 'redis') and hasattr(storage.redis, 'delete'):
        storage.redis.delete(key)

# Benchmark Configuration
ALGORITHMS = ["sliding_window", "fixed_window", "token_bucket", "leaky_bucket", "gcra"]
STORAGE_TYPES = ["async_memory", "sync_memory"]
if is_redis_available():
    STORAGE_TYPES.extend(["async_redis", "sync_redis"])
CONCURRENCY = 100
TOTAL_REQUESTS = 1000
LIMIT_VALUES = [100, 500, 1000]
FILL_LEVELS = [0.0, 0.5, 0.95]

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

    # Unique key for each benchmark run
    key = f"bench_{algorithm}_{storage_type}_{CONCURRENCY}_{limit}_{int(fill_level*100)}_{time.time_ns()}"
    rule_name = "bench"

    # Prefill to fill_level
    target = int(limit * fill_level)

    if is_async:
        loop.run_until_complete(prefill_limiter(limiter, key, rule_name, target))
    else:
        prefill_limiter_sync(limiter, key, rule_name, target)

    # Define the concurrent check function
    if is_async:
        sem = asyncio.Semaphore(CONCURRENCY)

        async def limited_check():
            async with sem:
                return await limiter.check(key, rule_name)

        async def run_checks():
            tasks = [limited_check() for _ in range(TOTAL_REQUESTS)]
            return await asyncio.gather(*tasks)

        # benchmark the async function
        result = benchmark(lambda: loop.run_until_complete(run_checks()))
    else:
        def sync_check():
            return limiter.check(key, rule_name)

        with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
            def sync_bench():
                futures = [executor.submit(sync_check) for _ in range(TOTAL_REQUESTS)]
                return [f.result() for f in futures]

            result = benchmark(sync_bench)

        # Clean up Redis keys if needed
    if "redis" in storage_type:
        if is_async:
            loop.run_until_complete(async_delete_redis_key(storage, key))
        else:
            sync_delete_redis_key(storage, key)