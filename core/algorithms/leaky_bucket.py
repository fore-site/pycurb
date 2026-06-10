import time
from .base import RateLimiterAlgorithm
from ..models import LimitRule, RateLimitResult
from ..storage.base import Storage

class LeakyBucketAlgorithm(RateLimiterAlgorithm):
    async def check(self, key: str, rule: LimitRule, storage: Storage) -> RateLimitResult:
        capacity = rule.capacity if rule.capacity is not None else rule.limit
        
        if capacity is None:
            raise ValueError("Leaky bucket algorithm requires 'capacity' or 'limit'.")
        
        if rule.leak_rate is not None:
            leak_rate = rule.leak_rate
        else:
            if rule.window is None:
                raise ValueError("Leaky bucket algorithm requires 'leak_rate' or 'window'.")
            leak_rate = capacity / rule.window

        if leak_rate <= 0:
            raise ValueError(f"leak_rate must be positive, got {leak_rate}")
        
        now = time.time()
        storage_key = f"{rule.name}:{key}"
        allowed, remaining, reset_at = await storage.leaky_bucket(
            key=storage_key, capacity=capacity, leak_rate=leak_rate, now=now
        )
        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_at=reset_at,
            limit=capacity,
            retry_after=None,
            rule_name=rule.name
        )