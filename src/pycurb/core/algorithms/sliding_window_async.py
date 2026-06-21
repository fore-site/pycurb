import time
from .base_async import AsyncRateLimiterAlgorithm
from ..models import LimitRule, RateLimitResult
from ..storage import AsyncStorage


class AsyncSlidingWindowAlgorithm(AsyncRateLimiterAlgorithm):
    async def check(
        self, key: str, rule: LimitRule, storage: AsyncStorage
    ) -> RateLimitResult:
        if rule.limit is None or rule.window is None:
            raise ValueError("Sliding window algorithm requires 'limit' and 'window'.")

        now = time.time()
        storage_key = f"{rule.name}:{key}"
        allowed, remaining, reset_at = await storage.sliding_window(
            key=storage_key, window=rule.window, limit=rule.limit, now=now
        )
        retry_after = max(0, int(reset_at - time.time()))
        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_at=reset_at,
            limit=rule.limit,
            retry_after=retry_after if not allowed else None,
            rule_name=rule.name,
        )
