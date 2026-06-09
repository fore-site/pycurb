import time
from .base import RateLimiterAlgorithm
from ..models import LimitRule, RateLimitResult
from  ..storage.base import Storage

class SlidingWindowAlgorithm(RateLimiterAlgorithm):
    async def check(self, key: str, rule: LimitRule, storage: Storage) -> RateLimitResult:
        if rule.limit is None or rule.window is None:
            raise ValueError("Sliding window algorithm requires 'limit' and 'window'.")
        now = time.time()
        allowed, remaining, reset_at = await storage.sliding_window(
            key=key, window=rule.window, limit=rule.limit, now=now)
        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_at=reset_at,
            limit=rule.limit,
            retry_after=None,
            rule_name=rule.name
        )