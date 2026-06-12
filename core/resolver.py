from typing import Dict, List, Optional
from .models import LimitRule
import asyncio
import threading

class AsyncRuleResolver:
    """
    Async rule resolver that stores rules in memory and allows dynamic addition/update.
    Implements the callable interface expected by RateLimiter.
    """

    def __init__(self, initial_rules: Optional[List[LimitRule]] = None):
        self._rules: Dict[str, LimitRule] = {}
        self._lock = asyncio.Lock()

        if initial_rules:
            for rule in initial_rules:
                self._rules[rule.name] = rule

    async def add_rule(self, rule: LimitRule) -> None:
        """Add or replace a rule by name."""
        async with self._lock:
            self._rules[rule.name] = rule

    async def remove_rule(self, name: str) -> None:
        """Remove a rule."""
        async with self._lock:
            self._rules.pop(name, None)

    async def __call__(self, name: str) -> LimitRule:
        async with self._lock:
            if name not in self._rules:
                raise ValueError(f"Rule '{name}' not found")
            return self._rules[name]


class RuleResolver:
    """
    Sync rule resolver that stores rules in memory and allows dynamic addition/update.
    Implements the callable interface expected by RateLimiter.
    """

    def __init__(self, initial_rules: Optional[List[LimitRule]] = None):
        self._rules: Dict[str, LimitRule] = {}
        self._lock = threading.RLock()

        if initial_rules:
            for rule in initial_rules:
                self._rules[rule.name] = rule

    def add_rule(self, rule: LimitRule) -> None:
        """Add or replace a rule by name."""
        with self._lock:
            self._rules[rule.name] = rule

    def remove_rule(self, name: str) -> None:
        """Remove a rule."""
        with self._lock:
            self._rules.pop(name, None)

    def __call__(self, name: str) -> LimitRule:
        with self._lock:
            if name not in self._rules:
                raise ValueError(f"Rule '{name}' not found")
            return self._rules[name]