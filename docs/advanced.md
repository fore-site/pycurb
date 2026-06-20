Topics for power users: composite rules, dynamic rule management, resolvers, and async support.

## Composite rules

[`RateLimiter.check`](api.md#pycurb.core.limiter.RateLimiter.check) accepts a single rule name or a list of rule names. When multiple rules are provided, all must allow the request; the returned [`RateLimitResult`](api.md#pycurb.core.models.RateLimitResult) corresponds to the most restrictive rule (smallest `remaining` / earliest `reset_at`). This allows layering limits (per-user + per-API-key + global).

## Dynamic rules & resolvers

Use [`RuleResolver`](api.md#pycurb.core.resolver.RuleResolver) / [`AsyncRuleResolver`](api.md#pycurb.core.resolver.AsyncRuleResolver) for in-memory mutable rule sets. Implement your own resolver to source rules from a database or config service.
Use [`RuleResolver`](api.md#pycurb.core.resolver.RuleResolver) for in-memory mutable rule sets (see the API Reference for async resolvers). Implement your own resolver to source rules from a database or config service.

```python
from pycurb.core.resolver import RuleResolver
resolver = RuleResolver(initial_rules=[...])
# See: https://docs/pycurb/api.html#pycurb.core.limiter.RateLimiter
limiter = RateLimiter(storage, resolver=resolver)
resolver.add_rule(new_rule)
```

## Async vs Sync

pycurb provides [`RateLimiter`](api.md#pycurb.core.limiter.RateLimiter) for sync code and [`AsyncRateLimiter`](api.md#pycurb.core.limiter_async.AsyncRateLimiter) for async code. Use matching adapters/decorators — mixing async views with sync limiters (or vice-versa) will raise `TypeError`.

## Choosing time source and observing behavior

- Redis backends can use `use_redis_time` to rely on server time to avoid client clock skew.
- Use `fallback_storage` and `fail_open` to control behavior on Redis failures.

