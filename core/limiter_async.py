import inspect
from typing import Dict, List, Callable, Union, cast
from .models import LimitRule, RateLimitResult
from .storage import AsyncStorage
from .resolver import AsyncRuleResolver
from .algorithms import (
    AsyncRateLimiterAlgorithm,
    AsyncSlidingWindowAlgorithm,
    AsyncFixedWindowAlgorithm,
    AsyncTokenBucketAlgorithm,
    AsyncLeakyBucketAlgorithm
)

class AsyncRateLimiter:
    """Async core rate limiter engine"""

    def __init__(
            self, 
            storage: AsyncStorage, 
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
            # static rule list
            self.rule_resolver = AsyncRuleResolver(rules_or_resolver)
        else:
            self.rule_resolver = cast(AsyncRuleResolver, rules_or_resolver)

        self.algorithms: Dict[str, AsyncRateLimiterAlgorithm] = {
            "sliding_window": AsyncSlidingWindowAlgorithm(),
            "fixed_window": AsyncFixedWindowAlgorithm(),
            "token_bucket": AsyncTokenBucketAlgorithm(),
            "leaky_bucket": AsyncLeakyBucketAlgorithm(),
        }

    @classmethod
    async def from_resolver(cls, storage: AsyncStorage, resolver: Callable[[str], LimitRule]):
        return cls(storage, resolver)

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