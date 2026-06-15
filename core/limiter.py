from typing import Dict, List, Callable, Optional, Union
from .models import LimitRule, RateLimitResult
from .storage import Storage
from .resolver import RuleResolver
from .algorithms import (
    RateLimiterAlgorithm,
    SlidingWindowAlgorithm,
    FixedWindowAlgorithm,
    TokenBucketAlgorithm,
    LeakyBucketAlgorithm,
    GcraAlgorithm
)

class RateLimiter:
    """Core rate limiter engine."""

    def __init__(self, 
                 storage: Storage, 
                 rules: Optional[List[LimitRule]] = None,
                 resolver: Optional[Callable[[str], LimitRule]] = None
        ):
        """
        Initialize the rate limiter

        Args:
            storage: A storage backend (e.g MemoryStorage, RedisStorage)
            rules: A list of LimitRule objects.
            resolver: A custom rule resolver instance.
        """
        if rules is not None and resolver is not None:
            raise ValueError("Provide either 'rules' or 'resolver'. Not both.")

        self.storage = storage

        if resolver is not None:
            self.rule_resolver = resolver
        else:
            self.rule_resolver = RuleResolver(rules or [])            

        self.algorithms: Dict[str, RateLimiterAlgorithm] = {
            "sliding_window": SlidingWindowAlgorithm(),
            "fixed_window": FixedWindowAlgorithm(),
            "token_bucket": TokenBucketAlgorithm(),
            "leaky_bucket": LeakyBucketAlgorithm(),
            "gcra": GcraAlgorithm()
        }

    @classmethod
    def from_resolver(cls, storage: Storage, resolver: Callable[[str], LimitRule]):
        return cls(storage, resolver=resolver)

    def add_rule(self, rule: LimitRule) -> None:
        """Add or replace a rule"""
        if not hasattr(self.rule_resolver, 'add_rule'):
            raise TypeError("The rule resolver does not support dynamic rule addition")
        self.rule_resolver.add_rule(rule)     # type: ignore
    
    def remove_rule(self, name: str) -> None:
        """Remove a rule by name"""
        if not hasattr(self.rule_resolver, "remove_rule"):
            raise TypeError("The rule resolver does not support dynamic rule removal")
        self.rule_resolver.remove_rule(name)      # type: ignore

    def check(self, key: str, rule_names: Union[str, List[str]]) -> RateLimitResult:
        """
        Check if a request with the given key is allowed under the named rule(s).

        Args:
            key: A unique identifier for the client (e.g IP, client_id, API key)
            rule_names: The name of the limit rule to apply. Also accepts multiple rules.

        Returns:
            RateLimitResult: Decision and metadata

        Raises:
            ValueError: If the rule name(s) is unknown or algorithm is not supported.
        """
        
        if isinstance(rule_names, str):
            return self._check_single(key, rule_names)
        results = []
        for name in rule_names:
            res = self._check_single(key, name)
            if not res.allowed:
                return res
            results.append(res)

        return min(results, key=lambda r : (r.remaining, r.reset_at))

    def _check_single(self, key: str, rule_name: str) -> RateLimitResult:
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