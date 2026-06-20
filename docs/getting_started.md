Quick steps to add rate limiting with pycurb.

## Create a storage and limiter (sync example)

Using [`MemoryStorage`](api.md#pycurb.core.storage.memory.MemoryStorage), [`RateLimiter`](api.md#pycurb.core.limiter.RateLimiter) and [`LimitRule`](api.md#pycurb.core.models.LimitRule).

```python
from pycurb.core import MemoryStorage, RateLimiter, LimitRule

storage = MemoryStorage()
rules = [LimitRule(name="api", algorithm="sliding_window", limit=100, window=60)]
limiter = RateLimiter(storage=storage, rules=rules)
```

## Create a storage and limiter (Async example)

Using [`AsyncMemoryStorage`](api.md#pycurb.core.storage.memory.AsyncMemoryStorage), [`AsyncRateLimiter`](api.md#pycurb.core.limiter.AsyncRateLimiter) and [`LimitRule`](api.md#pycurb.core.models.LimitRule).

```python
from pycurb.core import AsyncMemoryStorage, AsyncRateLimiter, LimitRule

storage = AsyncMemoryStorage()
rules = [LimitRule(name="api", algorithm="sliding_window", limit=100, window=60)]
limiter = AsyncRateLimiter(storage=storage, rules=rules)
```

## Check a key programmatically (see [`RateLimiter.check`](api.md#pycurb.core.limiter.RateLimiter.check))

```python
result = limiter.check("1.2.3.4", "api")
if result.allowed:
	# proceed
else:
	# handle limit exceeded
```

## Using decorators / adapters

- Flask decorator example (sync):

```python
from pycurb.adapters.flask.decorators import rate_limit

@app.route("/data")
@rate_limit(limiter, rule_name="api")
def data():
	return {"ok": True}
```

- FastAPI dependency example (async):

```python
from pycurb.adapters.fastapi.dependencies import rate_limiter

app.get("/data")(depends=rate_limiter(limiter_async, "api"))
```

## Using the decorator with shorthand `limit_str`

The unified `rate_limit` decorator supports creating a rule lazily from a shorthand string like `"100/m"` (100 per minute). See [parse_rate_limit_string](api.md#pycurb.utils.parse_rate_limit_string) for supported formats.
