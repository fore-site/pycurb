pycurb ships with in-memory and Redis-backed storage implementations (sync and async variants). Storage implementations provide a consistent set of atomic operations used by algorithms:

- `sliding_window(key, window, limit, now)`
- `fixed_window(key, window, limit, now)`
- `token_bucket(key, capacity, refill_rate, now)`
- `leaky_bucket(key, capacity, leak_rate, now)`
- `gcra(key, capacity, refill_rate, now)`

## MemoryStorage

- Implementation: [`MemoryStorage`](api.md#pycurb.core.storage.memory.MemoryStorage) and [`AsyncMemoryStorage`](api.md#pycurb.core.storage.memory.AsyncMemoryStorage)— fast, local, non-persistent.
- Use for development, single-process deployments, or when persistence is unnecessary.

Example:

```python
from pycurb.core.storage import MemoryStorage
storage = MemoryStorage()
```

## RedisStorage

- Implementation: [`RedisStorage`](api.md#pycurb.core.storage.redis.RedisStorage) and [`AsyncRedisStorage`](api.md#pycurb.core.storage.redis_async.AsyncRedisStorage).
- Provides accurate, distributed counters using Lua scripts; recommended for multi-process production deployments.
- Options: `key_prefix`, `use_redis_time` (use Redis server time for tighter clock skew tolerance. False by default), `fallback_storage` (fallback to another Storage instance.), and `fail_open` (allow or deny requests on Redis errors. Deny by default).

Example (sync):

```python
import redis
from pycurb.core.storage import RedisStorage

client = redis.Redis(host="localhost", port=6379)
storage = RedisStorage(client, key_prefix="ratelimit:")
```

Example (Sync) with connection pool:

```python
import redis
from pycurb.core.storage import RedisStorage

_sync_redis_pool = None

def get_redis_pool():
    global _sync_redis_pool
    if _sync_redis_pool is None:
        _sync_redis_pool = redis.ConnectionPool(
            host='localhost',
            port=6379,
            max_connections=10,
            decode_responses=True,
        )
    return _sync_redis_pool

pool = get_redis_pool()
client = redis.Redis(connection_pool=pool)
storage = RedisStorage(client, key_prefix="ratelimit:", use_redis_time=False, fail_open=False)
```

Example with fallback to memory on Redis errors:

```python
from pycurb.core.storage import RedisStorage, MemoryStorage
memory = MemoryStorage()
redis_storage = RedisStorage(client, fallback_storage=memory)
```

Example with fail open on Redis errors:

```python
from pycurb.core.storage import RedisStorage, MemoryStorage
memory = MemoryStorage()
redis_storage = RedisStorage(client, fail_open=True)
```

## Best practices

- Prefer Redis for distributed systems and high traffic.
- Enable `use_redis_time` to avoid relying on client clocks when accurate server time matters.
- When using Redis in production, consider `fallback_storage` and `fail_open` to control behavior during partial outages.
