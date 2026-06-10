from typing import Dict, List, Callable, Union
from .models import LimitRule, RateLimitResult
from .storage.base_sync import StorageSync
from .algorithms import (
    RateLimiterAlgorithmSync,
    SlidingWindowAlgorithmSync,
    FixedWindowAlgorithmSync,
    TokenBucketAlgorithmSync,
    LeakyBucketAlgorithmSync,
)

class RateLimiterSync:
    """Sync core rate limiter engine (for WSGI frameworks)."""

    def __init__(self, 
                 storage: StorageSync, 
                 rules_or_resolver: Union[List[LimitRule], Callable[[str], LimitRule]]
        ):
        self.storage = storage

        if isinstance(rules_or_resolver, list):
            rule_map: Dict[str, LimitRule] = {rule.name: rule for rule in rules_or_resolver}
            self.rule_resolver = lambda name: rule_map.get(name)
        else:
            self.rule_resolver = rules_or_resolver

        self.algorithms: Dict[str, RateLimiterAlgorithmSync] = {
            "sliding_window": SlidingWindowAlgorithmSync(),
            "fixed_window": FixedWindowAlgorithmSync(),
            "token_bucket": TokenBucketAlgorithmSync(),
            "leaky_bucket": LeakyBucketAlgorithmSync(),
        }

    def check(self, key: str, rule_name: str) -> RateLimitResult:
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
        rule = self.rule_resolver(rule_name)
        if rule is None:
            raise ValueError(f"Rule '{rule_name}' not found")
        algo = self.algorithms.get(rule.algorithm)
        if algo is None:
            raise ValueError(f"Unsupported algorithm '{rule.algorithm}' for rule '{rule_name}'")
        return algo.check(key, rule, self.storage)