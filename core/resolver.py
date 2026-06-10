from typing import Dict, Callable
from .models import LimitRule

class MutableRuleResolver:
    """
    A rule resolver that stores rules in memory and allows dynamic addition/update.
    Implements the callable interface expected by RateLimiter.
    """

    def __init__(self):
        self._rules: Dict[str, LimitRule] = {}

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

def static_rule_resolver(rules: list[LimitRule]) -> Callable[[str], LimitRule]:
    """
    Create a resolver from a static list of rules.
    Useful for backward compatibility.
    """
    rule_map = {rule.name: rule for rule in rules}
    def resolver(name: str) -> LimitRule:
        if name not in rule_map:
            raise ValueError(f"Rule '{name}' not found")
        return rule_map[name]
    return resolver