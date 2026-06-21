Quick steps to add rate limiting with pycurb.

## Create a rule

Create a list of [`LimitRule`](api.md#pycurb.core.models.LimitRule) object(s) for the rate-limiter to use. A rule consists of a name (to reference globally), an algorithm, and algorithm parameters. The rule must always be a list before being passed into the limiter, even if it is just a single rule.

```python
from pycurb.core import LimitRule
rule = [
	LimitRule(name="rule1", algorithm="fixed_window", limit=100, window=120)
	]

rules = [
	LimitRule(name="rule2", algorithm="sliding_window", limit=100, window=120),
	LimitRule(name="rule3", algorithm="token_bucket", capacity=100, refill_rate=20),
	LimitRule(name="rule4", algorithm="leaky_bucket", capacity=100, leak_rate=10),
	LimitRule(name="rule5", algorithm="gcra", capacity=300, refill_rate=50)
	]

```

## Create a storage and limiter (sync example)

Using [`MemoryStorage`](api.md#pycurb.core.storage.memory.MemoryStorage), [`RateLimiter`](api.md#pycurb.core.limiter.RateLimiter) and [`LimitRule`](api.md#pycurb.core.models.LimitRule).

```python
from pycurb.core import MemoryStorage, RateLimiter

storage = MemoryStorage()
limiter = RateLimiter(storage=storage, rules=rules)
```

## Create a storage and limiter (Async example)

Using [`AsyncMemoryStorage`](api.md#pycurb.core.storage.memory_async.AsyncMemoryStorage), [`AsyncRateLimiter`](api.md#pycurb.core.limiter_async.AsyncRateLimiter) and [`LimitRule`](api.md#pycurb.core.models.LimitRule).

```python
from pycurb.core import AsyncMemoryStorage, AsyncRateLimiter

storage = AsyncMemoryStorage()
rules = [LimitRule(name="api", algorithm="sliding_window", limit=100, window=60)]
limiter_async = AsyncRateLimiter(storage=storage, rules=rule)
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

## Using adapters (Flask / Django / FastAPI)

pycurb provides lightweight adapters to integrate the limiter into WSGI / ASGI frameworks. The adapters are thin wrappers that:

- expose a decorator for sync frameworks (Flask, Django views),
- expose middleware you can mount globally, and
- expose a dependency/helper for async frameworks (FastAPI).

The adapters do not add extra runtime behaviour: they call into your `RateLimiter`/`AsyncRateLimiter` and translate results into HTTP responses and headers. Below are practical examples

### Common concepts

- `key_extractor`: a callable that returns the client identifier (IP, API key, user id). If you do not provide one, the adapters default to `ip_extractor`.

- Response headers: adapters set `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` on allowed responses and `Retry-After` on 429 responses.

Note: FastAPI dependency adapter only sets the `Retry-After` header.

- Composite rules: The adapters accept a single rule name or a list of rule names (e.g. `['global', 'strict']`). All rules must allow for the request to succeed.

### Flask (sync)

Use the `rate_limit` decorator or the `RateLimit` middleware.

Example using decorator:

```python
from flask import Flask, jsonify
from pycurb.core import RateLimiter, MemoryStorage, LimitRule
from pycurb.adapters.flask import rate_limit, ip_extractor, api_key_extractor

storage = MemoryStorage()
rules = [LimitRule(name='global', algorithm='sliding_window', limit=2, window=10),
		 LimitRule(name='strict', algorithm='fixed_window', limit=1, window=10)]
limiter = RateLimiter(storage, rules)

app = Flask(__name__)

@app.route('/')
@rate_limit(limiter, 'global', key_extractor=ip_extractor)
def home():
	return jsonify({'ok': True})

@app.route('/strict')
@rate_limit(limiter, 'strict', key_extractor=api_key_extractor)
def strict():
	return jsonify({'ok': True})
```

Middleware usage (global application):

```python
from pycurb.adapters.flask import RateLimit

app = Flask(__name__)
RateLimit(app, limiter, 'global', key_extractor=ip_extractor)
```

Advanced options:

- You can pass `on_limit` to the decorator to return a custom response when limited.
- The decorator/middleware will raise or return a 429 when the limit is exceeded and include `Retry-After` and `X-RateLimit-*` headers.

### Django (sync)

Django usage mirrors Flask but uses a helper to create middleware classes and a decorator for views. Example:

```python
from pycurb.core import RateLimiter, MemoryStorage, LimitRule
from pycurb.adapters.django import rate_limit, create_rate_limit_middleware, ip_extractor

storage = MemoryStorage()
rules = [LimitRule(name='global', algorithm='sliding_window', limit=2, window=10)]
limiter = RateLimiter(storage, rules)

# Create a middleware class you can insert into Django's MIDDLEWARE stack

MiddlewareClass = create_rate_limit_middleware(limiter, 'global', key_extractor=ip_extractor)

# Or use the decorator on a function-based view
@rate_limit(limiter, 'global', key_extractor=ip_extractor)
def my_view(request):
	return JsonResponse({'ok': True})
```

### FastAPI (async)

FastAPI support includes a middleware `RateLimitMiddleware` and a dependency helper `rate_limiter` you can use with `Depends(...)`.

Middleware example (global rule):

```python
from fastapi import FastAPI
from pycurb.core import AsyncRateLimiter, AsyncMemoryStorage, LimitRule
from pycurb.adapters.fastapi import RateLimitMiddleware, ip_extractor

storage = AsyncMemoryStorage()
rules = [LimitRule(name='global', algorithm='sliding_window', limit=2, window=10)]
limiter = AsyncRateLimiter(storage, rules)

app = FastAPI()
app.add_middleware(RateLimitMiddleware, limiter=limiter, rule_name='global', key_extractor=ip_extractor)

@app.get('/')
async def home():
	return {'ok': True}
```

Dependency example (per-endpoint rule):

```python
from fastapi import Depends
from pycurb.adapters.fastapi import rate_limiter, api_key_extractor

@app.get('/strict')
async def strict(_=Depends(rate_limiter(limiter, 'strict', key_extractor=api_key_extractor))):
	return {'ok': True}
```

Composite rule example (global + strict):

```python
@app.get('/composite')
async def composite(_=Depends(rate_limiter(limiter, ['global', 'strict'], key_extractor=ip_extractor))):
	return {'ok': True}
```

### Adapter extractor helpers

Common extractors included with adapters:

- `ip_extractor(request)` — extracts client IP (uses X-Forwarded-For when present).
- `api_key_extractor(request)` — reads `X-API-Key` header or other configured locations.
- `user_id_extractor(request)` — extracts authenticated user id when available.

You can also pass a custom callable that accepts the framework request object and returns a string key.
