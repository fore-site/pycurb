import pytest
from typing import cast
from ...core.resolver import MutableRuleResolver
from ...core import (
    RateLimiter, RateLimiterSync,
    MutableRuleResolver, static_rule_resolver,
    rate_limit, RateLimitExceeded,
    arg_extractor, LimitRule
)
from ...core.storage import MemoryStorage, MemoryStorageSync

# Helpers

def create_async_limiter(rules=None):
    storage = MemoryStorage()
    if rules is None:
        resolver = MutableRuleResolver()
    else:
        if isinstance(rules, list):
            resolver = static_rule_resolver(rules)
        else:
            resolver = rules
    return RateLimiter(storage, resolver)

def create_sync_limiter(rules=None):
    storage = MemoryStorageSync()
    if rules is None:
        resolver = MutableRuleResolver()
    else:
        if isinstance(rules, list):
            resolver = static_rule_resolver(rules)
        else:
            resolver = rules
    return RateLimiterSync(storage, resolver)

# Async Tests

class TestAsyncRateLimitDecorator:
    async def test_named_rule_with_key_extractor(self):
        limiter = create_async_limiter()
        # Add a rule manually
        resolver = limiter.rule_resolver
        mutable_resolver = cast(MutableRuleResolver, resolver)
        mutable_resolver.add_rule(LimitRule(name="test", algorithm="fixed_window", limit=2, window=10))
        
        @rate_limit(limiter, rule_name="test", key_extractor=lambda user: str(user))
        async def func(user: str):
            return "ok"
        
        assert await func("a") == "ok"
        assert await func("a") == "ok"
        with pytest.raises(RateLimitExceeded):
            await func("a")
        # Different key still allowed
        assert await func("b") == "ok"

    async def test_inline_rule_with_arg_extractor(self):
        limiter = create_async_limiter()  # mutable resolver
        # key_extractor uses keyword argument 'uid'
        @rate_limit(limiter, limit_str="3/5s", key_extractor=arg_extractor("uid"))
        async def func(uid: str):
            return "ok"
        
        for _ in range(3):
            assert await func(uid="x") == "ok"
        with pytest.raises(RateLimitExceeded):
            await func(uid="x")
        # Different uid allowed
        assert await func(uid="y") == "ok"

    async def test_inline_rule_custom_algorithm(self):
        limiter = create_async_limiter()
        @rate_limit(limiter, limit_str="2/10s", algorithm="token_bucket", key_extractor=lambda uid: uid)
        async def func(uid: str):
            return "ok"
        
        assert await func("a") == "ok"
        assert await func("a") == "ok"
        with pytest.raises(RateLimitExceeded):
            await func("a")

    async def test_no_key_extractor_raises_type_error(self):
        limiter = create_async_limiter()
        with pytest.raises(TypeError, match="key_extractor must be provided"):
            @rate_limit(limiter, limit_str="10/s")  # missing key_extractor
            async def func():
                pass

    async def test_raise_on_limit_false(self):
        limiter = create_async_limiter()
        resolver = limiter.rule_resolver
        mutable_resolver = cast(MutableRuleResolver, resolver)
        mutable_resolver.add_rule(LimitRule(name="test", algorithm="fixed_window", limit=1, window=10))
        @rate_limit(limiter, rule_name="test", key_extractor=lambda: "same", raise_on_limit=False)
        async def func():
            return "data"
        
        assert await func() == "data"
        assert await func() is None  # rate limited, returns None

    async def test_invalid_rule_name_raises_value_error(self):
        limiter = create_async_limiter()
        @rate_limit(limiter, rule_name="nonexistent", key_extractor=lambda: "key")
        async def func():
            pass
        with pytest.raises(ValueError, match="Rule 'nonexistent' not found"):
            await func()

    async def test_invalid_limit_str_raises_value_error(self):
        limiter = create_async_limiter()
        with pytest.raises(ValueError, match="Invalid rate limit format"):
            @rate_limit(limiter, limit_str="invalid", key_extractor=lambda: "key")
            async def func():
                pass

    async def test_limit_str_with_static_resolver_raises_type_error(self):
        # Create limiter with static resolver (no add_rule)
        rule = LimitRule(name="dummy", algorithm="fixed_window", limit=10, window=60)
        limiter = create_async_limiter(rules=[rule])
        with pytest.raises(TypeError, match="does not support dynamic rule addition"):
            @rate_limit(limiter, limit_str="5/s", key_extractor=lambda: "key")
            async def func():
                pass

    async def test_key_isolation_between_different_functions(self):
        limiter = create_async_limiter()
        @rate_limit(limiter, limit_str="2/10s", key_extractor=lambda: "same")
        async def func1():
            return 1
        @rate_limit(limiter, limit_str="2/10s", key_extractor=lambda: "same")
        async def func2():
            return 2
        
        assert await func1() == 1
        assert await func1() == 1
        with pytest.raises(RateLimitExceeded):
            await func1()
        # func2 has its own rule (different name) so still allowed
        assert await func2() == 2
        assert await func2() == 2
        with pytest.raises(RateLimitExceeded):
            await func2()

# Sync Tests
class TestSyncRateLimitDecorator:
    def test_named_rule(self):
        limiter = create_sync_limiter()
        resolver = limiter.rule_resolver
        mutable_resolver = cast(MutableRuleResolver, resolver)
        mutable_resolver.add_rule(LimitRule(name="test", algorithm="fixed_window", limit=1, window=10))
        @rate_limit(limiter, rule_name="test", key_extractor=lambda: "key")
        def func():
            return "ok"
        
        assert func() == "ok"
        with pytest.raises(RateLimitExceeded):
            func()

    def test_inline_rule(self):
        limiter = create_sync_limiter()
        @rate_limit(limiter, limit_str="2/5s", key_extractor=arg_extractor("uid"))
        def func(uid: str):
            return uid
        
        assert func(uid="a") == "a"
        assert func(uid="a") == "a"
        with pytest.raises(RateLimitExceeded):
            func(uid="a")
        assert func(uid="b") == "b"

    def test_no_key_extractor_raises(self):
        limiter = create_sync_limiter()
        with pytest.raises(TypeError):
            @rate_limit(limiter, limit_str="10/s")
            def func():
                pass

    def test_raise_on_limit_false(self):
        limiter = create_sync_limiter()
        resolver = limiter.rule_resolver
        mutable_resolver = cast(MutableRuleResolver, resolver)
        mutable_resolver.add_rule(LimitRule(name="test", algorithm="fixed_window", limit=1, window=10))
        @rate_limit(limiter, rule_name="test", key_extractor=lambda: "same", raise_on_limit=False)
        def func():
            return "data"
        
        assert func() == "data"
        assert func() is None

    def test_invalid_rule_name(self):
        limiter = create_sync_limiter()
        @rate_limit(limiter, rule_name="missing", key_extractor=lambda: "key")
        def func():
            pass
        with pytest.raises(ValueError):
            func()

    def test_invalid_limit_str(self):
        limiter = create_sync_limiter()
        with pytest.raises(ValueError):
            @rate_limit(limiter, limit_str="bad", key_extractor=lambda: "key")
            def func():
                pass

    def test_limit_str_with_static_resolver_raises(self):
        rule = LimitRule(name="dummy", algorithm="fixed_window", limit=10, window=60)
        limiter = create_sync_limiter(rules=[rule])
        with pytest.raises(TypeError):
            @rate_limit(limiter, limit_str="5/s", key_extractor=lambda: "key")
            def func():
                pass

    def test_key_isolation(self):
        limiter = create_sync_limiter()
        @rate_limit(limiter, limit_str="1/10s", key_extractor=arg_extractor("uid"))
        def func(uid: str):
            return uid
        
        assert func(uid="a") == "a"
        with pytest.raises(RateLimitExceeded):
            func(uid="a")
        assert func(uid="b") == "b"