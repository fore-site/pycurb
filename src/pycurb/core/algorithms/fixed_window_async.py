import time
import math
from .base_async import AsyncRateLimiterAlgorithm
from ..models import LimitRule, RateLimitResult
from ..storage import AsyncStorage


class AsyncFixedWindowAlgorithm(AsyncRateLimiterAlgorithm):
    async def check(
        self, key: str, rule: LimitRule, storage: AsyncStorage
    ) -> RateLimitResult:
        if rule.limit is None or rule.window is None:
            raise ValueError("Fixed window algorithm requires 'limit' and 'window'.")

        now = time.time()
        storage_key = f"{rule.name}:{key}"
        allowed, remaining, reset_at = await storage.fixed_window(
            key=storage_key, window=rule.window, limit=rule.limit, now=now
        )
        retry_after = max(0, math.ceil(reset_at - now))
        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_at=reset_at,
            limit=rule.limit,
            retry_after=retry_after if not allowed else None,
            rule_name=rule.name,
        )
