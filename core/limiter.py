from typing import Dict, List
from .models import LimitRule, RateLimitResult
from .storage import Storage
from .algorithms import (
    RateLimiterAlgorithm,
    SlidingWindowAlgorithm,
    FixedWindowAlgorithm,
    TokenBucketAlgorithm,
    LeakyBucketAlgorithm
)

class RateLimiter:
    """Async core rate limiter engine"""

    def __init__(self, storage: Storage, rules: List[LimitRule]):
        """
        Initialize the rate limiter

        Args:
            storage: A storage backend (e.g MemoryStorage, RedisStorage)
            rules: A list of LimitRule objects. Each rule must have a unique name
        """
        self.storage = storage
        self.rules: Dict[str, LimitRule] = {rule.name: rule for rule in rules}
        self.algorithms: Dict[str, RateLimiterAlgorithm] = {
            "sliding_window": SlidingWindowAlgorithm(),
            "fixed_window": FixedWindowAlgorithm(),
            "token_bucket": TokenBucketAlgorithm(),
            "leaky_bucket": LeakyBucketAlgorithm(),
        }

    async def check(self, key: str, rule_name: str) -> RateLimitResult:
        """
        Check if a request with the given key is allowed under the named rule.

        Args:
            key: A unique identifier for the client (e.g IP, client_id, API key)
            rule_name: The name of the limit rule to apply

        Returns:
            RateLimitResult: Decision and metadata

        Raises:
            ValueError: If the rule name is unknown or algorithm is not supported.
        """
        rule = self.rules.get(rule_name)
        if rule is None:
            raise ValueError(f"Rule '{rule_name}' not found.")
        
        algorithm = self.algorithms.get(rule.algorithm)
        if algorithm is None:
            raise ValueError(f"Unsupported algorithm '{rule.algorithm}' for rule '{rule_name}'")
        return await algorithm.check(key=key, rule=rule, storage=self.storage)