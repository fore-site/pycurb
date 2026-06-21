Topics for power users: composite rules, dynamic rule management, resolvers, and async support.

## Composite rules

[`RateLimiter.check`](api.md#pycurb.core.limiter.RateLimiter.check) accepts a single rule name or a list of rule names. When multiple rules are provided, all must allow the request; the returned [`RateLimitResult`](api.md#pycurb.core.models.RateLimitResult) corresponds to the most restrictive rule (smallest `remaining` / earliest `reset_at`). This allows layering limits (per-user + per-API-key + global).

### Sequential evaluation & no atomicity

When you pass a list of rule names, the rules are evaluated sequentially. Each rule updates its own storage state as it is evaluated. If a later rule denies the request, the earlier rules have already consumed their quota – there is no rollback.

**Example**: If you check `["per_minute", "per_hour"]` and `per_hour` denies, the `per_minute` counter has already been incremented. This can lead to over‑consumption under high concurrency.

**Mitigation**: Place the most restrictive rule first in the list to minimise the chance of partial updates.

**Note**: Atomic multi‑rule checks are not supported out of the box. If you need atomicity, consider:

- Combining limits with similar semantics (recommended: same algorithm) into a single composite rule (e.g., `limit = min(per_minute, per_hour)`).
- Implementing a custom storage backend with transactional multi-check.
- Using a Lua script (for Redis) that checks and updates all keys atomically.

## Dynamic rules & resolvers

Use [`RuleResolver`](api.md#pycurb.core.resolver.RuleResolver) / [`AsyncRuleResolver`](api.md#pycurb.core.resolver.AsyncRuleResolver) for in-memory mutable rule sets. Implement your own resolver to source rules from a database or config service.

```python
from pycurb.core.resolver import RuleResolver
from pycurb.core import LimitRule

resolver = RuleResolver()
limiter = RateLimiter(storage, resolver=resolver)
new_rule = LimitRule(name="global", algorithm="gcra", capacity=200, refill_rate=30)

resolver.add_rule(new_rule)
```

### Custom resolvers must be callable

Any custom resolver must be callable: `resolver(rule_name) -> LimitRule`. If you are using the `limit_str` feature in the [`@rate_limit`](api.md#pycurb.core.decorators.rate_limit) decorator, your resolver must also implement:

```python

def add_rule(self, rule: LimitRule) -> None:
    ...
```

Without `add_rule`, the decorator will raise a `TypeError` when you try to create a rule lazily from a shorthand string.

Example of a minimal custom resolver:

```python

class MyResolver:
    def __init__(self):
        self.\_rules = {}

    def __call__(self, name: str) -> LimitRule:
        if name not in self._rules:
            raise ValueError(f"Rule '{name}' not found")
        return self._rules[name]

    def add_rule(self, rule: LimitRule) -> None:
        self._rules[rule.name] = rule

    def remove_rule(self, name: str) -> None:
        self._rules.pop(name, None)
```

### Resolvers must support `add_rule` for `limit_str`

The `@rate_limit(limiter, limit_str="100/s", ...)` decorator creates a rule dynamically and adds it to the resolver. For this to work, your resolver must implement an `add_rule` method.

The default [`RuleResolver`](api.md#pycurb.core.resolver.RuleResolver) and [`AsyncRuleResolver`](api.md#pycurb.core.resolver.AsyncRuleResolver) support this.

If you provide a custom resolver that does not have add_rule, the decorator will fail with a `TypeError`.

## Metadata Field in [`LimitRule`](api.md#pycurb.core.models.LimitRule)

The [`LimitRule`](api.md#pycurb.core.models.LimitRule) model includes an optional `metadata` field:

```python
from pycurb.core import LimitRule

rule = LimitRule(
    name="api",
    algorithm="sliding_window",
    limit=100,
    window=60,
    metadata={"tier": "premium", "description": "API rate limit for premium users"}
)
```

### Purpose

The `metadata` field is not used by the core rate limiter – it is provided for application‑specific annotations. You can attach any arbitrary data to a rule without affecting its behaviour.

### Common Use Cases

- Rule classification – attach labels like "priority", "tier", "team", or "owner".

- Observability – add a "description" or "version" to help with debugging and monitoring.

- Conditional logic in adapters – use `metadata` in a custom resolver or framework adapter to influence behaviour (e.g., different error messages for different tiers).

- Configuration management – when loading rules from a database or YAML, store extra fields that your application needs.

### Example: Using Metadata in a Resolver

```python

class TieredResolver:
    def __call__(self, name: str) -> LimitRule:
        rule = self._rules[name]
        tier = rule.metadata.get("tier", "free")
        if tier == "premium":
            # Return a higher‑limit rule for premium users
            return LimitRule(name=name, algorithm="sliding_window", limit=1000, window=60)
        return rule
```

### Note

The `metadata` field is ignored by all algorithms and storage backends. It does not affect rate‑limiting decisions – it's purely for user‑defined data.

## Multi‑tier headers

When using composite rules (multiple rules in one check()), the response headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`) reflect the most restrictive allowed rule:

If all rules allow, the returned [`RateLimitResult`](api.md#pycurb.core.models.RateLimitResult) is the one with the smallest `remaining` (and earliest `reset_at` as tie‑breaker).

If any rule denies, the request is denied and the `reset_at` from the first denied rule is used.

This ensures that clients see the strictest quota information, which is the most useful for them to determine when they can retry.

## Async vs Sync

Pycurb provides [`RateLimiter`](api.md#pycurb.core.limiter.RateLimiter) for sync code and [`AsyncRateLimiter`](api.md#pycurb.core.limiter_async.AsyncRateLimiter) for async code. Use matching adapters/decorators — mixing async views with sync limiters (or vice-versa) will raise `TypeError`.

## Choosing time source and observing behavior

- Redis backends can use `use_redis_time` to rely on server time to avoid client clock skew.
- Use `fallback_storage` and `fail_open` to control behavior on Redis failures.
