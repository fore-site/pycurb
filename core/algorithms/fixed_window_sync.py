import time
from .base_sync import RateLimiterAlgorithmSync
from ..models import LimitRule, RateLimitResult
from ..storage.base_sync import StorageSync

class FixedWindowAlgorithmSync(RateLimiterAlgorithmSync):
    def check(self, key: str, rule: LimitRule, storage: StorageSync) -> RateLimitResult:
        if rule.limit is None or rule.window is None:
            raise ValueError("Fixed window algorithm requires 'limit' and 'window'.")
        
        now = time.time()
        storage_key = f"{rule.name}:{key}"
        allowed, remaining, reset_at = storage.fixed_window(
            key=storage_key, window=rule.window, limit=rule.limit, now=now
        )
        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_at=reset_at,
            limit=rule.limit,
            retry_after=None,
            rule_name=rule.name
        )