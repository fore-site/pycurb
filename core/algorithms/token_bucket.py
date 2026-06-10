import time
from .base import RateLimiterAlgorithm
from ..models import LimitRule, RateLimitResult
from ..storage.base import Storage

class TokenBucketAlgorithm(RateLimiterAlgorithm):
    async def check(self, key: str, rule: LimitRule, storage: Storage) -> RateLimitResult:
        capacity = rule.capacity if rule.capacity is not None else rule.limit
        if capacity is None:
            raise ValueError("Token bucket algorithm requires 'capacity' or 'limit'.")
        
        if rule.refill_rate is not None:
            refill_rate = rule.refill_rate
        else:
            if rule.window is None:
                raise ValueError("Token bucket algorithm requires 'refill_rate' or 'window'.")
            refill_rate = capacity / rule.window

        if refill_rate <= 0:
            raise ValueError(f"refill_rate must be positive, got {refill_rate}.")
        
        now = time.time()
        storage_key = f"{rule.name}:{key}"
        allowed, remaining, reset_at = await storage.token_bucket(
            key=storage_key, capacity=capacity, refill_rate=refill_rate, now=now
        )
        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_at=reset_at,
            limit=capacity,
            retry_after=None,
            rule_name=rule.name
        )