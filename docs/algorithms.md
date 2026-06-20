This page describes the rate-limiting algorithms implemented by pycurb and the configuration options each algorithm requires.

- **Purpose**: choose an algorithm based on traffic shape and accuracy vs. memory/performance tradeoffs.

## Supported algorithms

- `sliding_window` — Accurate sliding-window counter built on timestamped events. Requires `limit` and `window` (seconds). Good for precision with modest storage.

- `fixed_window` — Simpler fixed window counters. Requires `limit` and `window`. Uses less storage but can produce short bursts at window boundaries.

- `token_bucket` — Token bucket supporting burst capacity and steady refill. Requires `capacity` (or `limit` fallback) and `refill_rate` (tokens/second) or `window` fallback to derive refill rate.

- `leaky_bucket` — Queue-like smoothing (leaky bucket). Requires `capacity` (or `limit` fallback) and `leak_rate` (requests/second) or `window` fallback to derive `leak_rate`.

- `gcra` — Generic Cell Rate Algorithm (GCRA) for precise rate pacing with burst allowance. Requires `capacity` (or `limit` fallback) and `refill_rate` (or `window` fallback to derive `rate`).

`limit` and `window` fallbacks for non-window algorithms, while okay, are only recommended when using `limit_str` argument in [`rate_limit`](api.md#pycurb.core.decorators.rate_limit) decorator. If you have the option to configure `capacity` and `rate` directly, do so.

## Configuration examples

Create a [`LimitRule`](api.md#pycurb.core.models.LimitRule):

```python
from pycurb.core.models import LimitRule

# Sliding window: 100 requests per 60 seconds
rule = LimitRule(name="api:sliding", algorithm="sliding_window", limit=100, window=60)

# Token bucket: capacity 50, refill 1 token/sec
tb = LimitRule(name="api:token", algorithm="token_bucket", capacity=50, refill_rate=1.0)
```

## When to pick which algorithm

- Use `sliding_window` when you need fair, per-request accuracy across any time boundary.

- Use `fixed_window` when simplicity and minimal state are important and occasional short bursts are acceptable.

- Use `token_bucket` for classic burst allowance with controlled refill and predictable long-term throughput.

- Use `leaky_bucket` to smooth bursty producers into a steady outgoing rate.

- Use `gcra` when you want strong pacing guarantees (works well for protecting downstream services that require evenly spread requests).
