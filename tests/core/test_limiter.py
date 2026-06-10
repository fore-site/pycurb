import pytest
from ...core import RateLimiter, RateLimiterSync, LimitRule
from ...core.algorithms import sliding_window as sw_module


BASE_TIME = 1_700_000_000.25
RESET_AT = BASE_TIME + 10


class AsyncSpyStorage:
    def __init__(self, response=(True, 4, RESET_AT)):
        self.response = response
        self.calls = []

    async def sliding_window(self, **kwargs):
        self.calls.append(("sliding_window", kwargs))
        return self.response

    async def fixed_window(self, **kwargs):
        self.calls.append(("fixed_window", kwargs))
        return self.response

    async def token_bucket(self, **kwargs):
        self.calls.append(("token_bucket", kwargs))
        return self.response

    async def leaky_bucket(self, **kwargs):
        self.calls.append(("leaky_bucket", kwargs))
        return self.response


class SyncSpyStorage:
    def __init__(self, response=(True, 4, RESET_AT)):
        self.response = response
        self.calls = []

    def sliding_window(self, **kwargs):
        self.calls.append(("sliding_window", kwargs))
        return self.response

    def fixed_window(self, **kwargs):
        self.calls.append(("fixed_window", kwargs))
        return self.response

    def token_bucket(self, **kwargs):
        self.calls.append(("token_bucket", kwargs))
        return self.response

    def leaky_bucket(self, **kwargs):
        self.calls.append(("leaky_bucket", kwargs))
        return self.response


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_check_uses_correct_algorithm_and_rule(self, monkeypatch):
        # Mock time
        monkeypatch.setattr(sw_module.time, "time", lambda: BASE_TIME)
        storage = AsyncSpyStorage(response=(True, 4, RESET_AT))
        rule = LimitRule(name="test_rule", algorithm="sliding_window", limit=5, window=60)
        limiter = RateLimiter(storage, [rule])  # type: ignore[arg-type]

        result = await limiter.check("key", "test_rule")

        # Verify storage call
        assert storage.calls == [
            ("sliding_window", {"key": f"{rule.name}:key", "limit": 5, "window": 60, "now": BASE_TIME})
        ]
        assert result.allowed is True
        assert result.remaining == 4
        assert result.rule_name == "test_rule"

    @pytest.mark.asyncio
    async def test_unknown_rule_raises_value_error(self):
        storage = AsyncSpyStorage()
        limiter = RateLimiter(storage, [])  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="Rule 'unknown' not found"):
            await limiter.check("key", "unknown")

    @pytest.mark.asyncio
    async def test_unsupported_algorithm_raises_value_error(self):
        storage = AsyncSpyStorage()
        # Create a rule with an algorithm that is not in the registry
        rule = LimitRule.model_construct(name="bad", algorithm="unsupported", limit=10, window=60)
        limiter = RateLimiter(storage, [rule])  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="Unsupported algorithm 'unsupported'"):
            await limiter.check("key", "bad")

class TestRateLimiterSync:
    def test_check_uses_correct_algorithm_and_rule(self, monkeypatch):
        monkeypatch.setattr(sw_module.time, "time", lambda: BASE_TIME)
        storage = SyncSpyStorage(response=(True, 4, RESET_AT))
        rule = LimitRule(name="test_rule_sync", algorithm="sliding_window", limit=5, window=60)
        limiter = RateLimiterSync(storage, [rule])  # type: ignore[arg-type]

        result = limiter.check("key", "test_rule_sync")

        assert storage.calls == [
            ("sliding_window", {"key": f"{rule.name}:key", "limit": 5, "window": 60, "now": BASE_TIME})
        ]
        assert result.allowed is True
        assert result.remaining == 4

    def test_unknown_rule_raises_value_error(self):
        storage = SyncSpyStorage()
        limiter = RateLimiterSync(storage, [])  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="Rule 'unknown' not found"):
            limiter.check("key", "unknown")

    def test_unsupported_algorithm_raises_value_error(self):
        storage = SyncSpyStorage()
        rule = LimitRule.model_construct(name="bad", algorithm="unsupported", limit=10, window=60)
        limiter = RateLimiterSync(storage, [rule])  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="Unsupported algorithm 'unsupported'"):
            limiter.check("key", "bad")