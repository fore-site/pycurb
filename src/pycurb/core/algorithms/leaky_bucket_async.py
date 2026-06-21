import time
import math
from .base_async import AsyncRateLimiterAlgorithm
from ..models import LimitRule, RateLimitResult
from ..storage import AsyncStorage


class AsyncLeakyBucketAlgorithm(AsyncRateLimiterAlgorithm):
    async def check(
        self, key: str, rule: LimitRule, storage: AsyncStorage
    ) -> RateLimitResult:
        capacity = rule.capacity if rule.capacity is not None else rule.limit

        if capacity is None:
            raise ValueError("Leaky bucket algorithm requires 'capacity' or 'limit'.")

        if rule.leak_rate is not None:
            leak_rate = rule.leak_rate
        else:
            if rule.window is None:
                raise ValueError(
                    "Leaky bucket algorithm requires 'leak_rate' or 'window'."
                )
            leak_rate = capacity / rule.window

        if leak_rate <= 0:
            raise ValueError(f"leak_rate must be positive, got {leak_rate}")

        now = time.time()
        storage_key = f"{rule.name}:{key}"
        allowed, remaining, reset_at = await storage.leaky_bucket(
            key=storage_key, capacity=capacity, leak_rate=leak_rate, now=now
        )
        retry_after = max(0, math.ceil(reset_at - now))
        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_at=reset_at,
            limit=capacity,
            retry_after=retry_after if not allowed else None,
            rule_name=rule.name,
        )
