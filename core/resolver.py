from typing import Dict
from .models import LimitRule

class MutableRuleResolver:
    """A rule resolver that stores rules in memory and allows dynamic addition/update."""

    def __init__(self):
        self._rules: Dict[str, LimitRule] = {}

    def add_rule(self, rule: LimitRule) -> None:
        """Add or replace a rule by name."""
        self._rules[rule.name] = rule

    def remove_rule(self, name: str) -> None:
        """Remove a rule."""
        self._rules.pop(name, None)

    def __call__(self, name: str) -> LimitRule:
        """Resolve rule by name. Raises KeyError if not found."""
        return self._rules[name]