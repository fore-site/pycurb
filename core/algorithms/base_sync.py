from abc import ABC, abstractmethod
from ..models import LimitRule, RateLimitResult
from ..storage.base_sync import StorageSync

class RateLimiterAlgorithmSync(ABC):
    """Abstract base for all rate limiting algorithms. Synchronous version (WSGI compatible)"""

    @abstractmethod
    def check(self, key: str, rule: LimitRule, storage: StorageSync) -> RateLimitResult:
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