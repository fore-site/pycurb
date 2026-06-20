**API Reference**

Quick links:

- [pycurb.core.models](#pycurb.core.models)
- [pycurb.core.storage](#pycurb.core.storage)
- [pycurb.core.limiter](#pycurb.core.limiter)
- [pycurb.core.limiter_async](#pycurb.core.limiter_async)
- [pycurb.core.resolver](#pycurb.core.resolver)
- [pycurb.core.decorators](#pycurb.core.decorators)
- [pycurb.utils](#pycurb.utils)

<a id="pycurb.core.models"></a>

## pycurb.core.models

::: pycurb.core.models.LimitRule

::: pycurb.core.models.RateLimitResult

::: pycurb.core.models.RateLimitHeaders

::: pycurb.core.models.RateLimitExceeded

<a id="pycurb.core.storage"></a>

## pycurb.core.storage

::: pycurb.core.storage.base.Storage

::: pycurb.core.storage.base_async.AsyncStorage

::: pycurb.core.storage.memory.MemoryStorage

::: pycurb.core.storage.memory_async.AsyncMemoryStorage

::: pycurb.core.storage.redis.RedisStorage

::: pycurb.core.storage.redis_async.AsyncRedisStorage

<a id="pycurb.core.limiter"></a>

## pycurb.core.limiter

::: pycurb.core.limiter.RateLimiter

::: pycurb.core.limiter.RateLimiter.check

::: pycurb.core.limiter.RateLimiter.add_rule

::: pycurb.core.limiter.RateLimiter.remove_rule

<a id="pycurb.core.limiter_async"></a>

## pycurb.core.limiter_async

::: pycurb.core.limiter_async.AsyncRateLimiter

::: pycurb.core.limiter_async.AsyncRateLimiter.check

<a id="pycurb.core.resolver"></a>

## pycurb.core.resolver

::: pycurb.core.resolver.RuleResolver

::: pycurb.core.resolver.AsyncRuleResolver

<a id="pycurb.core.decorators"></a>

## pycurb.core.decorators

::: pycurb.core.decorators.rate_limit

::: pycurb.core.decorators.arg_extractor

<a id="pycurb.utils"></a>

## pycurb.utils

::: pycurb.utils.parse_rate_limit_string

::: pycurb.utils.parse_duration
