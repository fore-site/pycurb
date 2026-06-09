import time
from .base import RateLimiterAlgorithm
from ..models import LimitRule, RateLimitResult
from ..storage.base import Storage

class LeakyBucketAlgorithm(RateLimiterAlgorithm):
    async def check(self, key: str, rule: LimitRule, storage: Storage) -> RateLimitResult:
        capacity = rule.capacity if rule.capacity is not None else rule.limit
        leak_rate = rule.leak_rate
        if capacity is None:
            raise ValueError("Leaky bucket algorithm requires 'capacity' or 'limit'.")
        if leak_rate is None:
            raise ValueError("Leaky bucket algorithm requires 'leak_rate'.")
        if leak_rate <= 0:
            raise ValueError(f"leak_rate must be positive, got {leak_rate}")
        
        now = time.time()
        allowed, remaining, reset_at = await storage.leaky_bucket(
            key=key, capacity=capacity, leak_rate=leak_rate, now=now
        )
        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_at=reset_at,
            limit=capacity,
            retry_after=None,
            rule_name=rule.name
        )