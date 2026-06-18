from typing import Tuple

import pytest
import redis.exceptions
from pycurb.core.storage import MemoryStorage, RedisStorage

# Helper: Failing Redis Client
class FailingRedisClient:
    def __getattr__(self, name):
        def failing(*args, **kwargs):
            raise redis.exceptions.ConnectionError(f"Simulated Redis failure for {name}")
        return failing

# Spy Storage
class SpyStorage(MemoryStorage):
    def __init__(self):
        super().__init__()
        self.calls = []

    def sliding_window(self, key, window, limit, now):
        self.calls.append(("sliding_window", (key, window, limit, now)))
        return super().sliding_window(key, window, limit, now)

    def fixed_window(self, key, window, limit, now):
        self.calls.append(("fixed_window", (key, window, limit, now)))
        return super().fixed_window(key, window, limit, now)

    def token_bucket(self, key, capacity, refill_rate, now):
        self.calls.append(("token_bucket", (key, capacity, refill_rate, now)))
        return super().token_bucket(key, capacity, refill_rate, now)

    def leaky_bucket(self, key, capacity, leak_rate, now):
        self.calls.append(("leaky_bucket", (key, capacity, leak_rate, now)))
        return super().leaky_bucket(key, capacity, leak_rate, now)
    
    def gcra(self, key: str, capacity: int, rate: float, now: float) -> Tuple[bool, int, float]:
        self.calls.append(("gcra", (key, capacity, rate, now)))
        return super().gcra(key, capacity, rate, now)

# Tests

def test_sliding_window_fallback_to_memory_sync():
    spy = SpyStorage()
    failing_client = FailingRedisClient()
    storage = RedisStorage(failing_client, fallback_storage=spy, fail_open=False, use_redis_time=False) # type: ignore[arg-type]

    result = storage.sliding_window("test_key", 60, 100, 12345.0)

    assert len(spy.calls) == 1
    method_name, args = spy.calls[0]
    assert method_name == "sliding_window"
    assert args == ("test_key", 60, 100, 12345.0)
    assert result[0] is True

def test_fixed_window_fallback_to_memory_sync():
    spy = SpyStorage()
    failing_client = FailingRedisClient()
    storage = RedisStorage(failing_client, fallback_storage=spy, fail_open=False, use_redis_time=False) #type: ignore

    result = storage.fixed_window("test_key", 60, 100, 12345.0)

    assert len(spy.calls) == 1
    method_name, args = spy.calls[0]
    assert method_name == "fixed_window"
    assert args == ("test_key", 60, 100, 12345.0)
    assert result[0] is True

def test_token_bucket_fallback_to_memory_sync():
    spy = SpyStorage()
    failing_client = FailingRedisClient()
    storage = RedisStorage(failing_client, fallback_storage=spy, fail_open=False, use_redis_time=False) # type: ignore

    result = storage.token_bucket("test_key", 10, 2.0, 12345.0)

    assert len(spy.calls) == 1
    method_name, args = spy.calls[0]
    assert method_name == "token_bucket"
    assert args == ("test_key", 10, 2.0, 12345.0)
    assert result[0] is True
    assert result[1] == 9

def test_leaky_bucket_fallback_to_memory_sync():
    spy = SpyStorage()
    failing_client = FailingRedisClient()
    storage = RedisStorage(failing_client, fallback_storage=spy, fail_open=False, use_redis_time=False) # type: ignore

    result = storage.leaky_bucket("test_key", 5, 1.0, 12345.0)

    assert len(spy.calls) == 1
    method_name, args = spy.calls[0]
    assert method_name == "leaky_bucket"
    assert args == ("test_key", 5, 1.0, 12345.0)
    assert result[0] is True

def test_gcra_fallback_to_memory_sync():
    spy = SpyStorage()
    failing_client = FailingRedisClient()
    storage = RedisStorage(failing_client, fallback_storage=spy, fail_open=False)   # type: ignore

    result = storage.gcra("test_key", 10, 2.0, 12345.0)
    assert len(spy.calls) == 1

    method_name, args = spy.calls[0]
    assert method_name == "gcra"
    assert args == ("test_key", 10, 2.0, 12345.0)
    assert result[0] is True
    assert result[1] == 9


# Without fallback storage: fail_open / fail_closed

def test_fail_open_true_allows_request_sync():
    failing_client = FailingRedisClient()
    storage = RedisStorage(failing_client, fallback_storage=None, fail_open=True, use_redis_time=False) # type: ignore

    allowed, remaining, reset_at = storage.sliding_window("key", 60, 100, 12345.0)

    assert allowed is True
    assert remaining == 9999
    assert reset_at == 12345.0 + 3600

def test_fail_open_false_denies_request_sync():
    failing_client = FailingRedisClient()
    storage = RedisStorage(failing_client, fallback_storage=None, fail_open=False, use_redis_time=False)    # type: ignore

    allowed, remaining, reset_at = storage.sliding_window("key", 60, 100, 12345.0)

    assert allowed is False
    assert remaining == 0
    assert reset_at == float('inf')

# Parametrized test for all methods
@pytest.mark.parametrize("method_name,args", [
    ("sliding_window", ("key", 60, 100, 12345.0)),
    ("fixed_window", ("key", 60, 100, 12345.0)),
    ("token_bucket", ("key", 10, 2.0, 12345.0)),
    ("leaky_bucket", ("key", 5, 1.0, 12345.0)),
    ("gcra", ("key", 10, 2.0, 12345.0))
])
def test_all_methods_trigger_fallback_sync(method_name, args):
    spy = SpyStorage()
    failing_client = FailingRedisClient()
    storage = RedisStorage(failing_client, fallback_storage=spy, fail_open=False, use_redis_time=False) # type: ignore

    method = getattr(storage, method_name)
    result = method(*args)

    assert len(spy.calls) == 1
    call_method, call_args = spy.calls[0]
    assert call_method == method_name
    assert call_args == args