This page describes the rate-limiting algorithms implemented by pycurb and the configuration options each algorithm requires.

- **Purpose**: choose an algorithm based on traffic shape and accuracy vs. memory/performance tradeoffs.

## Supported algorithms

- `sliding_window`: Accurate sliding-window counter built on timestamped events. Requires `limit` and `window` (seconds). Good for precision with modest storage.

- `fixed_window`: Simpler fixed window counters. Requires `limit` and `window`. Uses less storage but can produce short bursts at window boundaries.

- `token_bucket`: Token bucket supporting burst capacity and steady refill. Requires `capacity` (or `limit` fallback) and `refill_rate` (tokens/second) or `window` fallback to derive refill rate.

- `leaky_bucket`: Queue-like smoothing (leaky bucket). Requires `capacity` (or `limit` fallback) and `leak_rate` (requests/second) or `window` fallback to derive `leak_rate`.

- `gcra`: Generic Cell Rate Algorithm (GCRA) for precise rate pacing with burst allowance. Requires `capacity` (or `limit` fallback) and `refill_rate` (or `window` fallback to derive `rate`).

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

## Algorithm Caveats

### Fixed Window: Boundary Burst Vulnerability

Fixed window allows up to limit requests in each aligned window. However, because the counter resets exactly at the window boundary, a client can send limit requests at the very end of one window and another limit requests at the very start of the next window, effectively achieving 2 \* limit requests in a very short time (e.g., within a few milliseconds).

Example:

    Limit = 100 requests per minute, windows aligned at 0s, 60s, 120s, …

    At 59.999s, the client sends 100 requests (within the first window).

    At 60.001s, the client sends another 100 requests (start of the next window).

    Total = 200 requests in ~2 ms, i.e double the intended limit.

Mitigation:

- Use sliding window if this burst behaviour is unacceptable for your use case.

- Use token bucket if you need precise burst control with a configurable capacity.

Fixed window is still a good choice for simple, low‑memory limiting where occasional boundary bursts are acceptable (e.g., internal rate limits, non‑critical APIs).

### Leaky Bucket: Lazy Refill Implementation (No Background Timers)

PyCurb implements the leaky bucket algorithm using a counter‑based, lazy refill approach. The bucket does not use a background timer or thread to drain requests. Instead, the queue size is recalculated on‑demand when a request arrives:

```text

queue = max(0, queue - (now - last_leak) * leak_rate)
```

This means:

- No background processes: The algorithm is purely event‑driven and does not waste resources.

- Fractional leaks are preserved: If only 0.6 of a request should have leaked, the fractional part is retained and applied to future calculations.

- Accurate even under high‑frequency requests: The bucket will eventually leak as expected, without the “never leaks” bug that occurs in naive integer‑only implementations.

Why this matters:

- You do not need to run a separate timer or cron job to drain the bucket.

- The algorithm is memory‑efficient (only stores a float for the current queue level and a timestamp).

- The behaviour is identical to a traditional leaky bucket, but without the overhead of a background thread.
