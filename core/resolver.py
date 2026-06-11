from typing import Dict, List, Optional
from .models import LimitRule

class RuleResolver:
    """
    A rule resolver that stores rules in memory and allows dynamic addition/update.
    Implements the callable interface expected by RateLimiter.
    """

    def __init__(self, initial_rules: Optional[List[LimitRule]] = None):
        self._rules: Dict[str, LimitRule] = {}
        if initial_rules:
            for rule in initial_rules:
                self._rules[rule.name] = rule

    def add_rule(self, rule: LimitRule) -> None:
        """Add or replace a rule by name."""
        self._rules[rule.name] = rule

    def remove_rule(self, name: str) -> None:
        """Remove a rule."""
        self._rules.pop(name, None)

    def __call__(self, name: str) -> LimitRule:
        if name not in self._rules:
            raise ValueError(f"Rule '{name}' not found")
        return self._rules[name]
