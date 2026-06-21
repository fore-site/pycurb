# PyCurb – A Framework‑Agnostic Rate Limiter for Python

[![CI](https://github.com/fore-site/pycurb/actions/workflows/test.yml/badge.svg)](https://github.com/fore-site/pycurb/actions)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![Documentation Status](https://readthedocs.org/projects/pycurb/badge/?version=latest)](https://pycurb.readthedocs.io/en/latest/?badge=latest)

**PyCurb** is a flexible, and easy‑to‑use rate‑limiting library for Python. It is desgined to be **framework‑agnostic**, i.e, used with FastAPI, Flask, Django, or even in plain scripts and CLI tools. It supports multiple algorithms, redis & in-memory storage backends, and has advanced features like composite (multi‑tier) limits, and dynamic rule updates.

## Algorithms

PyCurb implements five industry‑standard rate‑limiting algorithms, each suited for different traffic patterns. Choose the one that best fits your use case.

### 1. Sliding Window

The sliding window algorithm maintains a **queue of request timestamps** for each key. The window slides continuously; old timestamps (older than `now - window`) are discarded. At any moment, the number of requests in the window is the length of the queue.

- **Use case**: APIs where you need strict, real‑time limiting without the burstiness of fixed windows.
- **Parameters**: `limit` (max requests), `window` (duration in seconds).
- **Behaviour**: The window moves with every request; no abrupt resets.

**Example**  
Limit: `100 requests per minute`.  
At `t=10s`, a request arrives; its timestamp is stored. At `t=75s`, the window covers `[15s, 75s]`; any request older than `15s` is dropped. The count is the number of timestamps in that range.

`count = |{ t ∈ timestamps : t > now - window }|`  
Allowed if `count < limit`.

### 2. Fixed Window

Fixed window divides time into consecutive, non‑overlapping windows of length `window`. All requests within the same window are counted together. The counter resets at the start of each new window.

- **Use case**: Simple, memory‑efficient limiting for non‑critical APIs.
- **Parameters**: `limit` (max requests per window), `window` (duration in seconds).
- **Behaviour**: The counter resets abruptly at window boundaries.

**Example**  
Limit: `100 requests per minute`, windows start at `0s`, `60s`, `120s`, …  
At `t=10s`, the counter is in window `[0,60)`. At `t=75s`, a new window `[60,120)` begins and the counter resets to `0`.

`window_start = floor(now / window) * window`  
`counter` is stored for the current `window_start`.  
Allowed if `counter < limit`.

### 3. Token Bucket

The token bucket algorithm maintains a **bucket of tokens** that refills at a constant rate. Each request consumes one token. If the bucket has at least one token, the request is allowed; otherwise, it is denied.

- **Use case**: APIs that require a steady average rate with the ability to handle short bursts.
- **Parameters**: `capacity` (burst size), `refill_rate` (tokens per second).
- **Behaviour**: Allows bursts up to `capacity`; long‑term average is `refill_rate`.

**Example**  
Capacity = `10`, refill rate = `2 tokens/sec`.  
Initially, the bucket has `10` tokens. A client can send `10` requests immediately (burst). After that, the bucket refills at `2 tokens/sec`, so the client can sustain `2` requests per second over time.

`tokens = min(capacity, tokens + (now - last_refill) * refill_rate)`  
Allowed if `tokens >= 1`; then `tokens -= 1`.

### 4. Leaky Bucket

The leaky bucket algorithm models a **queue** that holds pending requests. Requests leak out of the queue at a constant rate (`leak_rate`). New requests are accepted only if the queue has free capacity.

- **Use case**: Smoothing bursty traffic to a constant output rate (e.g., for database writes or external API calls).
- **Parameters**: `capacity` (max queue size), `leak_rate` (requests per second).
- **Behaviour**: Smooths bursts; the output rate is constant.

**Example**  
Capacity = `5`, leak rate = `1 request/sec`.  
If `5` requests arrive at once, they fill the queue. They are then processed at `1 request/sec`. A new request arriving while the queue is full is dropped.

`leaked = floor((now - last_leak) * leak_rate)`  
`queue = max(0, queue - leaked)`  
Allowed if `queue < capacity`; then `queue += 1`.

### 5. GCRA – Generic Cell Rate Algorithm

GCRA (also known as the **leaky bucket with burst control**) uses a single state variable – the **Theoretical Arrival Time (TAT)** – to enforce both a rate and a burst size. It does not require a queue or background processes.

- **Use case**: High‑precision rate limiting where both burst and average rate must be controlled.
- **Parameters**: `capacity` (burst size), `refill_rate` (requests per second).
- **Behaviour**: Similar to token bucket but implemented with a single timestamp, making it extremely efficient.

**Example**  
Capacity = `10`, rate = `5 req/sec` → interval `T = 0.2s`, burst interval `τ = capacity * T = 2s`.  
The algorithm allows a request if `TAT ≤ now + τ`. After an allowed request, `TAT = max(TAT, now) + T`. This ensures that the average rate is `5 req/sec` and the burst is at most `10` requests.

`T = 1 / refill_rate`  
`τ = (capacity - 1) * T` _(using `capacity-1` to match the burst size exactly)_  
Allowed if `TAT ≤ now + τ`.  
If allowed: `TAT = max(TAT, now) + T`.

### Comparison Table

| Algorithm      | Burst Tolerance | Memory Usage        | Best For                           |
| -------------- | --------------- | ------------------- | ---------------------------------- |
| Sliding Window | Up to limit     | Medium (timestamps) | Precise window limits              |
| Fixed Window   | Up to limit     | Low (counter)       | Simple, low‑overhead limiting      |
| Token Bucket   | Configurable    | Low (2 floats)      | Burst‑tolerant APIs                |
| Leaky Bucket   | None (smooths)  | Low (2 floats)      | Constant‑rate processing           |
| GCRA           | Configurable    | Low (1 float)       | High‑precision, efficient limiting |

Choose the algorithm that aligns with your traffic pattern and resource constraints. All algorithms are fully configurable via the `LimitRule` model.

---

## Get Started

### Installation

Install the core package:

```
pip install pycurb
```

For redis as a storage backend, install:

```
pip install pycurb[redis]
```

For framework adapters (i.e Flask, Django, FastAPI), install the extras:

```
pip install pycurb[fastapi]
```

To install everything:

```
pip install pycurb[all]
```

### Basic Usage (Async)

```
import asyncio
import time
from pycurb.core import AsyncRateLimiter, AsyncMemoryStorage, LimitRule
```

1. Define a rule: 5 requests per 10 seconds

```
rule = LimitRule(
    name="api",
    algorithm="sliding_window",
    limit=5,
    window=10,
)
```

2. Set up storage and limiter

```
storage = AsyncMemoryStorage()
limiter = AsyncRateLimiter(storage, [rule])
```

3. Use it in your async function

```
async def fetch_data(user_id: str):
result = await limiter.check(user_id, "api")
if result.allowed:
    print(f"Allowed – remaining: {result.remaining}")
else:
    print(f"Denied – retry after: {result.retry_after}")

asyncio.run(fetch_data("user-123"))
```

### Basic Usage (Sync)

```
from pycurb.core import RateLimiter, MemoryStorage, LimitRule

storage = MemoryStorage()
limiter = RateLimiter(storage, [rule])

def handle_request(user_id: str):
    result = limiter.check(user_id, "api")
    if result.allowed:
        print("Request allowed")
    else:
        print(f"Rate limited. Retry after {result.retry_after} seconds.")
```

### Using the Decorator

The `@rate_limit` decorator wraps any sync or async function

```
from pycurb.core import rate_limit

@rate_limit(limiter, limit_str="5/10s", key_extractor=lambda user_id: str(user_id))
async def my_function(user_id: str):
    return "OK"
```

### Framework Adapters

Pycurb provides plug-and-play adapters for popular python frameworks

- FastAPI: Use the `RateLimitMiddleware` class or `rate_limiter` dependency
- Django: Use the `rate_limit` decorator or the `create_rate_limit_middleware` factory
- Flask: Use the `rate_limit` decorator or the `RateLimit` extension

---

## Links

- [Documentation](https://pycurb.readthedocs.io/en/latest)
