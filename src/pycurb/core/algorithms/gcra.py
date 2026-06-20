import time
from .base import RateLimiterAlgorithm
from ..models import LimitRule, RateLimitResult
from ..storage import Storage


class GcraAlgorithm(RateLimiterAlgorithm):
    def check(self, key: str, rule: LimitRule, storage: Storage) -> RateLimitResult:
        capacity = rule.capacity if rule.capacity is not None else rule.limit
        if capacity is None:
            raise ValueError("Gcra algorithm requires 'capacity' or 'limit'.")

        if rule.refill_rate is not None:
            rate = rule.refill_rate
        else:
            if rule.window is None:
                raise ValueError("Gcra algorithm requires rate equal to 'refill_rate'")
            rate = capacity / rule.window

        if rate <= 0:
            raise ValueError(f"rate must be positive, got {rate}")

        now = time.time()
        storage_key = f"{rule.name}:{key}"
        allowed, remaining, reset_at = storage.gcra(
            key=storage_key, capacity=capacity, rate=rate, now=now
        )

        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_at=reset_at,
            limit=capacity,
            retry_after=None,
            rule_name=rule.name,
        )
