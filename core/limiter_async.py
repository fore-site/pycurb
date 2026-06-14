import inspect
from typing import Dict, List, Callable, Optional
from .models import LimitRule, RateLimitResult
from .storage import AsyncStorage
from .resolver import AsyncRuleResolver
from .algorithms import (
    AsyncRateLimiterAlgorithm,
    AsyncSlidingWindowAlgorithm,
    AsyncFixedWindowAlgorithm,
    AsyncTokenBucketAlgorithm,
    AsyncLeakyBucketAlgorithm,
    AsyncGcraAlgorithm
)

class AsyncRateLimiter:
    """Async core rate limiter engine"""

    def __init__(
            self, 
            storage: AsyncStorage, 
            rules: Optional[List[LimitRule]] = None,
            resolver: Optional[Callable[[str], LimitRule]] = None
        ):
        """
        Initialize the rate limiter

        Args:
            storage: A storage backend (e.g MemoryStorage, RedisStorage)
            rules: A list of LimitRule objects 
            resolver: A rule resolver instance.
        """
        if rules is not None and resolver is not None:
            raise ValueError("Provide either 'rules' or 'resolver'. Not both.") 
        self.storage = storage

        if resolver is not None:
            self.rule_resolver = resolver
        else:
            self.rule_resolver = AsyncRuleResolver(rules or [])

        self.algorithms: Dict[str, AsyncRateLimiterAlgorithm] = {
            "sliding_window": AsyncSlidingWindowAlgorithm(),
            "fixed_window": AsyncFixedWindowAlgorithm(),
            "token_bucket": AsyncTokenBucketAlgorithm(),
            "leaky_bucket": AsyncLeakyBucketAlgorithm(),
            "gcra": AsyncGcraAlgorithm()
        }

    @classmethod
    async def from_resolver(cls, storage: AsyncStorage, resolver: Callable[[str], LimitRule]):
        return cls(storage, resolver=resolver)

    async def add_rule(self, rule: LimitRule) -> None:
        """Add or replace a rule"""
        if not hasattr(self.rule_resolver, 'add_rule'):
            raise TypeError("The rule resolver does not support dynamic rule addition")
        await self.rule_resolver.add_rule(rule)     # type: ignore
    
    async def remove_rule(self, name: str) -> None:
        """Remove a rule by name"""
        if not hasattr(self.rule_resolver, "remove_rule"):
            raise TypeError("The rule resolver does not support dynamic rule removal")
        await self.rule_resolver.remove_rule(name)      # type: ignore

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
        rule = self.rule_resolver(rule_name)
        rule_is_async = inspect.iscoroutine(rule)
        if rule is None:
            raise ValueError(f"Rule '{rule_name}' not found.")
        
        if rule_is_async:
            rule = await rule

        algorithm = self.algorithms.get(rule.algorithm)
        if algorithm is None:
            raise ValueError(f"Unsupported algorithm '{rule.algorithm}' for rule '{rule_name}'")
        return await algorithm.check(key=key, rule=rule, storage=self.storage)