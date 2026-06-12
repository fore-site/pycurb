from abc import ABC, abstractmethod
from ..models import LimitRule, RateLimitResult
from ..storage import AsyncStorage

class AsyncRateLimiterAlgorithm(ABC):
    """Async abstract base for all rate limiting algorithms."""

    @abstractmethod
    async def check(self, key: str, rule: LimitRule, storage: AsyncStorage) -> RateLimitResult:
        """
        Evaluate rate limit for a given key and rule.
        Args:
            key: Unique client identifier (extracted by adapter) prefixed with rule name
            rule: The limit rule applied
            storage: Storage backend for atomic counters
        
        Returns:
            RateLimitResult: Decision and metadata.
        """
        pass