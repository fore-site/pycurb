import pytest
from ...core import (
    RateLimiter, AsyncRateLimiter,
    RuleResolver, AsyncRuleResolver,
    LimitRule
)
from ...core.storage import MemoryStorage, AsyncMemoryStorage

# Helpers
def create_async_limiter(rules = None, resolver = None):
    storage = AsyncMemoryStorage()
    if rules is None and resolver is None:
        return AsyncRateLimiter(storage)
    if rules is not None:
        return AsyncRateLimiter(storage, rules=rules)
    return AsyncRateLimiter(storage, resolver=resolver)

def create_sync_limiter(rules =  None, resolver = None):
    storage = MemoryStorage()
    if rules is None and resolver is None:
        return RateLimiter(storage)
    if rules is not None:
        return RateLimiter(storage, rules=rules)
    return RateLimiter(storage, resolver=resolver)

# Async Tests

class TestAsyncManualUsage:
    @pytest.mark.asyncio
    async def test_static_rule_list(self):
        rule = LimitRule(name="test", algorithm="fixed_window", limit=2, window=10)
        limiter = create_async_limiter(rules=[rule])
        
        # Check within limit
        result = await limiter.check("key1", "test")
        assert result.allowed is True
        assert result.remaining == 1
        # Second request allowed
        result = await limiter.check("key1", "test")
        assert result.allowed is True
        assert result.remaining == 0
        # Third denied
        result = await limiter.check("key1", "test")
        assert result.allowed is False
        # Different key independent
        result = await limiter.check("key2", "test")
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_mutable_resolver(self):
        resolver = AsyncRuleResolver()
        limiter = create_async_limiter(resolver=resolver)
        rule = LimitRule(name="test", algorithm="sliding_window", limit=3, window=10)
        await resolver.add_rule(rule)
        
        for i in range(3):
            result = await limiter.check("key", "test")
            assert result.allowed is True
            assert result.remaining == 2 - i
        result = await limiter.check("key", "test")
        assert result.allowed is False

        # Replace rule with higher limit
        new_rule = LimitRule(name="test", algorithm="sliding_window", limit=5, window=10)
        await resolver.add_rule(new_rule)
        # Now should allow again (new window starts fresh or count reset)
        result = await limiter.check("key", "test")
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_remove_rule(self):
        limiter = create_async_limiter()
        rule = LimitRule(name="temp", algorithm="fixed_window", limit=1, window=10)
        
        await limiter.add_rule(rule)
        result = await limiter.check("key", "temp")
        assert result.allowed is True
        
        await limiter.remove_rule("temp")
        with pytest.raises(ValueError, match="Rule 'temp' not found"):
            await limiter.check("key", "temp")

    @pytest.mark.asyncio
    async def test_static_gcra_rule_list(self):
        rule = LimitRule(name="gcra_api", algorithm="gcra", capacity=2, refill_rate=1.0)
        limiter = create_async_limiter(rules=[rule])

        # Check within limit
        result = await limiter.check("key1", "gcra_api")
        assert result.allowed is True
        assert result.remaining == 1
        # Second request allowed
        result = await limiter.check("key1", "gcra_api")
        assert result.allowed is True
        assert result.remaining == 0
        # Third denied
        result = await limiter.check("key1", "gcra_api")
        assert result.allowed is False
        # Different key independent
        result = await limiter.check("key2", "gcra_api")
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_static_resolver_function(self):
        rules = [LimitRule(name="api", algorithm="token_bucket", capacity=5, refill_rate=1)]
        resolver = AsyncRuleResolver(rules)
        limiter = create_async_limiter(resolver=resolver)
        for i in range(5):
            result = await limiter.check("key", "api")
            assert result.allowed is True
        result = await limiter.check("key", "api")
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_rule_not_found(self):
        limiter = create_async_limiter([])
        with pytest.raises(ValueError, match="Rule 'unknown' not found"):
            await limiter.check("key", "unknown")

    @pytest.mark.asyncio
    async def test_key_extractor_not_needed_manual(self):
        # Manual usage passes key directly, no extractor needed.
        rule = LimitRule(name="test", algorithm="fixed_window", limit=1, window=10)
        limiter = create_async_limiter(rules=[rule])
        result = await limiter.check("alice", "test")
        assert result.allowed is True
        result = await limiter.check("alice", "test")
        assert result.allowed is False
        result = await limiter.check("bob", "test")
        assert result.allowed is True

# Sync Tests

class TestSyncManualUsage:
    def test_static_rule_list(self):
        rule = LimitRule(name="test", algorithm="fixed_window", limit=2, window=10)
        limiter = create_sync_limiter(rules=[rule])
        result = limiter.check("key", "test")
        assert result.allowed is True
        result = limiter.check("key", "test")
        assert result.allowed is True
        result = limiter.check("key", "test")
        assert result.allowed is False

    def test_static_gcra_rule_list(self):
        rule = LimitRule(name="gcra_api", algorithm="gcra", capacity=2, refill_rate=1.0)
        limiter = create_sync_limiter(rules=[rule])

        result = limiter.check("key", "gcra_api")
        assert result.allowed is True
        result = limiter.check("key", "gcra_api")
        assert result.allowed is True
        result = limiter.check("key", "gcra_api")
        assert result.allowed is False

    def test_mutable_resolver(self):
        resolver = RuleResolver()
        limiter = create_sync_limiter(resolver=resolver)
        rule = LimitRule(name="test", algorithm="fixed_window", limit=3, window=10)
        resolver.add_rule(rule)
        for i in range(3):
            result = limiter.check("key", "test")
            assert result.allowed is True
        result = limiter.check("key", "test")
        assert result.allowed is False

    def test_static_resolver_function(self):
        rules = [LimitRule(name="api", algorithm="token_bucket", capacity=2, refill_rate=1)]
        resolver = RuleResolver(rules)
        limiter = create_sync_limiter(resolver=resolver)
        result = limiter.check("key", "api")
        assert result.allowed is True
        result = limiter.check("key", "api")
        assert result.allowed is True
        result = limiter.check("key", "api")
        assert result.allowed is False

    def test_rule_not_found(self):
        limiter = create_sync_limiter([])
        with pytest.raises(ValueError):
            limiter.check("key", "missing")