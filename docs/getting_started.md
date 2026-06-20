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

Using [`AsyncMemoryStorage`](api.md#pycurb.core.storage.memory_async.AsyncMemoryStorage), [`AsyncRateLimiter`](api.md#pycurb.core.limiter_async.AsyncRateLimiter) and [`LimitRule`](api.md#pycurb.core.models.LimitRule).

```python
from pycurb.core import AsyncMemoryStorage, AsyncRateLimiter, LimitRule

storage = AsyncMemoryStorage()
rules = [LimitRule(name="api", algorithm="sliding_window", limit=100, window=60)]
limiter_async = AsyncRateLimiter(storage=storage, rules=rules)
```

## Check a key programmatically (see [`RateLimiter.check`](api.md#pycurb.core.limiter.RateLimiter.check))

```python
result = limiter.check("1.2.3.4", "api")
if result.allowed:
	# proceed
else:
	# handle limit exceeded
```

## Using the [`rate_limit`](api.md#pycurb.core.decorators.rate_limit) decorator with `rule_name`

The unified `rate_limit` decorator can be applied over a function, accepting existing rule or list of rules to use. It raises a [RateLimitExceeded](api.md#pycurb.core.models.RateLimitExceeded) if rate limit has been exceeded.

Example (Sync):

```python
from pycurb.core import rate_limit

@rate_limit(limiter=limiter, rule_name='api', key_extractor=lambda user_id: str(user_id))
def data(user_id: str):
	return {"status": "okay"}
```

Example (Async) with list of rules (composite):

```python
from pycurb.core import rate_limit

rules.append(LimitRule((name="global", algorithm="token_bucket", capacity=100, refill_rate=10)))

@rate_limit(limiter=limiter, ='10/s', rule_name=rules, key_extractor=lambda user_id: str(user_id))
def data(user_id: str):
	return {"status": "okay"}
```

## Using the [`rate_limit`](api.md#pycurb.core.decorators.rate_limit) decorator with shorthand `limit_str`

The unified `rate_limit` decorator also supports creating a rule lazily from a shorthand string like `"100/m"` (100 per minute). See [parse_rate_limit_string](api.md#pycurb.utils.parse_rate_limit_string) for supported formats.

Example (Sync):

```python
from pycurb.core import rate_limit

@rate_limit(limiter=limiter, limit_str='10/s', key_extractor=lambda user_id: str(user_id))
def data(user_id: str):
	return {"status": "okay"}
```

Example (Async):

```python
from pycurb.core import rate_limit

@rate_limit(limiter=limiter_async, limit_str='10/s', key_extractor=lambda user_id: str(user_id))
async def data(user_id: str):
	return {"status": "okay"}
```

You can also make use of the [arg_extractor](api.md#pycurb.core.decorators.arg_extractor) helper to extract key identifiers from the decorated function:

```python
from pycurb.core import rate_limit, arg_extractor

@rate_limit(limiter=limiter, limit_str='10/s', key_extractor=arg_extractor("uid"))
def data(uid: str):
	return {"status": "okay"}
```

## Using adapters

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
