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
	print(f"Retry after {result.retry_after} seconds.")

print(result.remaining)
# remaining requests/token in the current window/bucket
```

## Using the [`rate_limit`](api.md#pycurb.core.decorators.rate_limit) decorator with `rule_name`

The unified [`@rate_limit`](api.md#pycurb.core.decorators.rate_limit) decorator can be applied over a function, accepting existing rule or list of rules to use. It raises a [RateLimitExceeded](api.md#pycurb.core.models.RateLimitExceeded) if rate limit has been exceeded.

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

The unified [`@rate_limit`](api.md#pycurb.core.decorators.rate_limit) decorator also supports creating a rule lazily from a shorthand string like `"100/m"` (100 per minute). See [parse_rate_limit_string](api.md#pycurb.utils.parse_rate_limit_string) for supported formats.

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

### Important Notes

**`key_extractor` is mandatory**

The [`@rate_limit`](api.md#pycurb.core.decorators.rate_limit) decorator requires you to provide a `key_extractor` callable. There is no default – a built‑in default like `default` would cause all calls to share the same counter, making rate limiting useless.

Always define a `key_extractor` that returns a unique identifier for your client (e.g., user ID, IP address, API key).

```python

# Good: uses a unique user ID

@rate_limit(limiter, limit_str="10/s", key_extractor=lambda user_id: str(user_id))
def api_call(user_id: int):
	...

# Bad: missing key_extractor (will raise TypeError)

@rate_limit(limiter, limit_str="10/s")
def api_call(user_id: int):
	...
```

**[`@rate_limit`](api.md#pycurb.core.decorators.rate_limit) always raises [`RateLimitExceeded`](api.md#pycurb.core.models.RateLimitExceeded)**

When the rate limit is exceeded, the [`@rate_limit`](api.md#pycurb.core.decorators.rate_limit) decorator always raises [`RateLimitExceeded`](api.md#pycurb.core.models.RateLimitExceeded). You must handle the exception explicitly if you need to customise the behaviour (e.g., return a different response).

```python

from pycurb.core import rate_limit, RateLimitExceeded

@rate_limit(limiter, limit_str="10/s", key_extractor=lambda user: str(user))
def my_function(user: str):
return {"status": "ok"}

try:
result = my_function("alice")
except RateLimitExceeded as e:
print(f"Rate limited! Retry after {e.result.reset_at}")
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
