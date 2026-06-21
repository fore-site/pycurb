pycurb ships with in-memory and Redis-backed storage implementations (sync and async variants). Storage implementations provide a consistent set of atomic operations used by algorithms:

- `sliding_window(key, window, limit, now)`
- `fixed_window(key, window, limit, now)`
- `token_bucket(key, capacity, refill_rate, now)`
- `leaky_bucket(key, capacity, leak_rate, now)`
- `gcra(key, capacity, refill_rate, now)`

## MemoryStorage

- Implementation: [`MemoryStorage`](api.md#pycurb.core.storage.memory.MemoryStorage) and [`AsyncMemoryStorage`](api.md#pycurb.core.storage.memory_async.AsyncMemoryStorage)— fast, local, non-persistent.
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

Example with fallback to memory on Redis errors:

```python
from pycurb.core.storage import RedisStorage, MemoryStorage
memory = MemoryStorage()
redis_storage = RedisStorage(client, fallback_storage=memory)
```

## Advanced Redis Deployments

PyCurb’s Redis storage works with **Redis Cluster**, **Sentinel**, and **TLS** configurations. The library uses single‑key operations only, so it is fully compatible with Redis Cluster’s hash‑slot routing.

### Redis Cluster Example

```python
from redis.cluster import RedisCluster
client = RedisCluster(host='localhost', port=7000, decode_responses=True)
storage = RedisStorage(client)
```

### Redis Sentinel Example

```python

from redis.sentinel import Sentinel
sentinel = Sentinel([('sentinel1', 26379), ('sentinel2', 26379)], socket_timeout=0.1)
client = sentinel.master_for('mymaster', socket_timeout=0.1, decode_responses=True)
storage = RedisStorage(client)
```

### Redis TLS/SSL

```python

import redis
client = redis.Redis(host='localhost', port=6379, ssl=True, ssl_certfile='/path/to/cert.pem')
storage = RedisStorage(client)
```

## Best practices

- Prefer Redis for distributed systems and high traffic.
- Enable `use_redis_time` to avoid relying on client clocks when accurate server time matters.
- When using Redis in production, consider `fallback_storage` and `fail_open` to control behavior during partial outages.

## Important Caveats

### Redis `fail_open` – Default is False (Fail‑Closed)

The `fail_open` parameter controls what happens when Redis is unavailable and no fallback_storage is provided:

| `fail_open`       | Behaviour                              | When to use                                                                                                   |
| ----------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `False` (default) | All requests are denied (fail‑closed). | Default – Safe for security‑critical endpoints (login, payments, admin).                                      |
| `True`            | All requests are allowed (fail‑open).  | Only when availability is more important than accuracy (e.g., read‑only public APIs, non‑critical endpoints). |

**Warning:** Setting `fail_open=True` disables rate limiting during Redis outages. Use this only if you fully understand the security and abuse‑risk trade‑off.

```python

# Fail‑closed (default) – safe

storage = RedisStorage(client, fail_open=False)

# Fail‑open – allows all requests when Redis is down

storage = RedisStorage(client, fail_open=True)
```

### Redis Clock Skew – Use use_redis_time=True for Distributed Deployments

When running multiple application instances (e.g., multiple FastAPI workers, Kubernetes pods), their system clocks may drift. This can cause inconsistent rate‑limiting decisions across instances.

**Solution:** Enable `use_redis_time=True` to use Redis server time instead of the client’s local clock. Redis server time is authoritative and shared across all instances.

```python

storage = RedisStorage(client, use_redis_time=True)
```

**Trade‑off:** Each request adds one extra TIME command to the Lua script, which adds a small performance overhead (typically < 0.1 ms). For high‑throughput applications, measure the impact before enabling.

When to use:

- Multi‑instance deployments where clocks may drift.

- You need absolute consistency across instances.

Do not use:

- Single‑instance deployments (no clock skew).

- When you cannot afford the extra latency.

### Redis Connection Pooling – Essential for Sync Redis Performance

For synchronous Redis ([`RedisStorage`](api.md#pycurb.core.storage.redis.RedisStorage) with `redis.Redis`), always use a connection pool in production. Without pooling, each request creates and destroys a new connection, significantly increasing latency and reducing throughput.

Why it matters:

- Creating a new connection per request adds ~1–3 ms overhead.

- A connection pool reuses connections, reducing latency and improving throughput by 30–50% in our benchmarks.

Example (sync Redis with pooling):

```python

import redis
from pycurb.core.storage import RedisStorage

# Create a connection pool

pool = redis.ConnectionPool(
host='localhost',
port=6379,
max_connections=20, # Tune to your concurrency level
decode_responses=True,
)

# Reuse the pool across all storage instances

client = redis.Redis(connection_pool=pool)
storage = RedisStorage(client, key_prefix="ratelimit:")
```

For async Redis ([`AsyncRedisStorage`](api.md#pycurb.core.storage.redis_async.AsyncRedisStorage)):

The redis.asyncio client already manages its own connection pool internally. You do not need to create a separate pool unless you need custom tuning.
