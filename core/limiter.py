from typing import Dict, List, Callable, Union, cast
from .models import LimitRule, RateLimitResult
from .storage import Storage
from .resolver import RuleResolver
from .algorithms import (
    RateLimiterAlgorithm,
    SlidingWindowAlgorithm,
    FixedWindowAlgorithm,
    TokenBucketAlgorithm,
    LeakyBucketAlgorithm,
)

class RateLimiter:
    """Core rate limiter engine."""

    def __init__(self, 
                 storage: Storage, 
                 rules_or_resolver: Union[List[LimitRule], Callable[[str], LimitRule]]
        ):
        """
        Initialize the rate limiter

        Args:
            storage: A storage backend (e.g MemoryStorage, RedisStorage)
            rules_or_resolver: A list of LimitRule objects. Each rule must have a unique name
        """
        self.storage = storage

        if isinstance(rules_or_resolver, list):
            self.rule_resolver = RuleResolver(rules_or_resolver)
        else:
            self.rule_resolver = cast(RuleResolver, rules_or_resolver)

        self.algorithms: Dict[str, RateLimiterAlgorithm] = {
            "sliding_window": SlidingWindowAlgorithm(),
            "fixed_window": FixedWindowAlgorithm(),
            "token_bucket": TokenBucketAlgorithm(),
            "leaky_bucket": LeakyBucketAlgorithm(),
        }

    @classmethod
    def from_resolver(cls, storage: Storage, resolver: Callable[[str], LimitRule]):
        return cls(storage, resolver)

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