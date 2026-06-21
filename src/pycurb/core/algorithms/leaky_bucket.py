import time
from .base import RateLimiterAlgorithm
from ..models import LimitRule, RateLimitResult
from ..storage import Storage


class LeakyBucketAlgorithm(RateLimiterAlgorithm):
    def check(self, key: str, rule: LimitRule, storage: Storage) -> RateLimitResult:
        capacity = rule.capacity if rule.capacity is not None else rule.limit

        if capacity is None:
            raise ValueError("Leaky bucket algorithm requires 'capacity' or 'limit'.")

        if rule.leak_rate is not None:
            rate = rule.leak_rate
        else:
            if rule.window is None:
                raise ValueError(
                    "Leaky bucket algorithm requires 'leak_rate' or 'window'."
                )
            rate = capacity / rule.window

        if rate <= 0:
            raise ValueError(f"leak_rate must be positive, got {rate}")

        now = time.time()
        storage_key = f"{rule.name}:{key}"
        allowed, remaining, reset_at = storage.leaky_bucket(
            key=storage_key, capacity=capacity, leak_rate=rate, now=now
        )
        retry_after = max(0, int(reset_at - time.time()))
        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_at=reset_at,
            limit=capacity,
            retry_after=retry_after if not allowed else None,
            rule_name=rule.name,
        )
