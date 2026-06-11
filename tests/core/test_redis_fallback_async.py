import pytest
import redis.exceptions
from ...core.storage import MemoryStorage, RedisStorage

# Helper: Failing Redis Client (async)
class FailingRedisClient:
    def __getattr__(self, name):
        async def failing(*args, **kwargs):
            raise redis.exceptions.ConnectionError(f"Simulated Redis failure for {name}")
        return failing

# Spy Storage to record calls

class SpyStorage(MemoryStorage):
    def __init__(self):
        super().__init__()
        self.calls = []

    async def sliding_window(self, key, window, limit, now):
        self.calls.append(("sliding_window", (key, window, limit, now)))
        return await super().sliding_window(key, window, limit, now)

    async def fixed_window(self, key, window, limit, now):
        self.calls.append(("fixed_window", (key, window, limit, now)))
        return await super().fixed_window(key, window, limit, now)

    async def token_bucket(self, key, capacity, refill_rate, now):
        self.calls.append(("token_bucket", (key, capacity, refill_rate, now)))
        return await super().token_bucket(key, capacity, refill_rate, now)

    async def leaky_bucket(self, key, capacity, leak_rate, now):
        self.calls.append(("leaky_bucket", (key, capacity, leak_rate, now)))
        return await super().leaky_bucket(key, capacity, leak_rate, now)

# Tests
@pytest.mark.asyncio
async def test_sliding_window_fallback_to_memory():
    spy = SpyStorage()
    failing_client = FailingRedisClient()
    storage = RedisStorage(failing_client, fallback_storage=spy, fail_open=False, use_redis_time=False) # type: ignore[arg-type]

    result = await storage.sliding_window("test_key", 60, 100, 12345.0)

    assert len(spy.calls) == 1
    method_name, args = spy.calls[0]
    assert method_name == "sliding_window"
    assert args == ("test_key", 60, 100, 12345.0)
    # MemoryStorage starts empty: first request allowed
    assert result[0] is True

@pytest.mark.asyncio
async def test_fixed_window_fallback_to_memory():
    spy = SpyStorage()
    failing_client = FailingRedisClient()
    storage = RedisStorage(failing_client, fallback_storage=spy, fail_open=False, use_redis_time=False) # type: ignore[arg-type]

    result = await storage.fixed_window("test_key", 60, 100, 12345.0)

    assert len(spy.calls) == 1
    method_name, args = spy.calls[0]
    assert method_name == "fixed_window"
    assert args == ("test_key", 60, 100, 12345.0)
    assert result[0] is True

@pytest.mark.asyncio
async def test_token_bucket_fallback_to_memory():
    spy = SpyStorage()
    failing_client = FailingRedisClient()
    storage = RedisStorage(failing_client, fallback_storage=spy, fail_open=False, use_redis_time=False) # type: ignore[arg-type]

    result = await storage.token_bucket("test_key", 10, 2.0, 12345.0)

    assert len(spy.calls) == 1
    method_name, args = spy.calls[0]
    assert method_name == "token_bucket"
    assert args == ("test_key", 10, 2.0, 12345.0)
    # MemoryStorage token bucket starts full: first request allowed, remaining = capacity-1
    assert result[0] is True
    assert result[1] == 9  # capacity=10, remaining after consuming = 9

@pytest.mark.asyncio
async def test_leaky_bucket_fallback_to_memory():
    spy = SpyStorage()
    failing_client = FailingRedisClient()
    storage = RedisStorage(failing_client, fallback_storage=spy, fail_open=False, use_redis_time=False) # type: ignore[arg-type]

    result = await storage.leaky_bucket("test_key", 5, 1.0, 12345.0)

    assert len(spy.calls) == 1
    method_name, args = spy.calls[0]
    assert method_name == "leaky_bucket"
    assert args == ("test_key", 5, 1.0, 12345.0)
    assert result[0] is True

# Tests without fallback storage: fail_open / fail_closed

@pytest.mark.asyncio
async def test_fail_open_true_allows_request():
    failing_client = FailingRedisClient()
    storage = RedisStorage(failing_client, fallback_storage=None, fail_open=True, use_redis_time=False) # type: ignore[arg-type]

    allowed, remaining, reset_at = await storage.sliding_window("key", 60, 100, 12345.0)

    assert allowed is True
    assert remaining == 9999
    assert reset_at == 12345.0 + 3600

@pytest.mark.asyncio
async def test_fail_open_false_denies_request():
    failing_client = FailingRedisClient()
    storage = RedisStorage(failing_client, fallback_storage=None, fail_open=False, use_redis_time=False)    # type: ignore[arg-type]

    allowed, remaining, reset_at = await storage.sliding_window("key", 60, 100, 12345.0)

    assert allowed is False
    assert remaining == 0
    assert reset_at == float('inf')

# Test that all methods trigger fallback (parametrized)

@pytest.mark.asyncio
@pytest.mark.parametrize("method_name,args", [
    ("sliding_window", ("key", 60, 100, 12345.0)),
    ("fixed_window", ("key", 60, 100, 12345.0)),
    ("token_bucket", ("key", 10, 2.0, 12345.0)),
    ("leaky_bucket", ("key", 5, 1.0, 12345.0)),
])
async def test_all_methods_trigger_fallback(method_name, args):
    spy = SpyStorage()
    failing_client = FailingRedisClient()
    storage = RedisStorage(failing_client, fallback_storage=spy, fail_open=False, use_redis_time=False) # type: ignore[arg-type]

    method = getattr(storage, method_name)
    result = await method(*args)

    assert len(spy.calls) == 1
    call_method, call_args = spy.calls[0]
    assert call_method == method_name
    assert call_args == args