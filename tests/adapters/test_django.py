import pytest
from pycurb.core import RateLimiter, AsyncRateLimiter, MemoryStorage, AsyncMemoryStorage, LimitRule
from pycurb.adapters.django import (
    rate_limit,
    create_rate_limit_middleware,
    ip_extractor,
    user_id_extractor,
    api_key_extractor,
)
import time
import django
import json
from django.conf import settings

if not settings.configured:
    settings.configure(
        DEBUG=True,
        SECRET_KEY='test-secret-key',
        INSTALLED_APPS=[],
        MIDDLEWARE=[],
        ROOT_URLCONF=__name__,
        DEFAULT_CHARSET='utf-8',
    )
    django.setup()

from django.test import RequestFactory, Client
from django.http import JsonResponse

# Fixtures

@pytest.fixture
def limiter_sync():
    storage = MemoryStorage()
    rules = [
        LimitRule(name="global", algorithm="sliding_window", limit=2, window=10),
        LimitRule(name="strict", algorithm="fixed_window", limit=1, window=10),
        LimitRule(name="burst", algorithm="token_bucket", capacity=3, refill_rate=1.0),
        LimitRule(name="sliding", algorithm="sliding_window", limit=5, window=10),
        LimitRule(name="fixed", algorithm="fixed_window", limit=3, window=10),
        LimitRule(name="leaky", algorithm="leaky_bucket", capacity=2, leak_rate=1.0),
        LimitRule(name="gcra", algorithm="gcra", capacity=4, refill_rate=2.0),
    ]
    return RateLimiter(storage, rules)

@pytest.fixture
def limiter_async():
    storage = AsyncMemoryStorage()
    rules = [
        LimitRule(name="async_test", algorithm="sliding_window", limit=2, window=10),
    ]
    return AsyncRateLimiter(storage, rules)

@pytest.fixture
def factory():
    return RequestFactory()

@pytest.fixture
def client():
    return Client()

# Helper to create middleware class from limiter
def get_middleware_class(limiter, rule_name, key_extractor=ip_extractor):
    return create_rate_limit_middleware(limiter, rule_name, key_extractor)

# Tests for Decorator (sync views)
class TestSyncDecorator:
    def test_sliding_window_allows_within_limit(self, limiter_sync, factory):
        @rate_limit(limiter_sync, "sliding", key_extractor=ip_extractor)
        def view(request):
            return JsonResponse({"ok": True})

        request = factory.get("/")
        for i in range(5):
            response = view(request)
            assert response.status_code == 200
            # Headers are set by decorator
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers
            assert int(response.headers["X-RateLimit-Remaining"]) == 4 - i
        # 6th request denied
        response = view(request)
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    def test_fixed_window_allows_within_limit(self, limiter_sync, factory):
        @rate_limit(limiter_sync, "fixed", key_extractor=ip_extractor)
        def view(request):
            return JsonResponse({"ok": True})

        request = factory.get("/")
        for i in range(3):
            response = view(request)
            assert response.status_code == 200
            assert int(response.headers["X-RateLimit-Remaining"]) == 2 - i
        response = view(request)
        assert response.status_code == 429

    def test_token_bucket_allows_burst_then_refills(self, limiter_sync, factory):
        @rate_limit(limiter_sync, "burst", key_extractor=ip_extractor)
        def view(request):
            return JsonResponse({"ok": True})

        request = factory.get("/")
        for i in range(3):
            response = view(request)
            assert response.status_code == 200
            assert int(response.headers["X-RateLimit-Remaining"]) == 2 - i
        # 4th denied
        response = view(request)
        assert response.status_code == 429
        # Wait for refill
        time.sleep(1.1)
        response = view(request)
        assert response.status_code == 200
        assert int(response.headers["X-RateLimit-Remaining"]) == 0  # consumed, empty

    def test_leaky_bucket_allows_within_capacity(self, limiter_sync, factory):
        @rate_limit(limiter_sync, "leaky", key_extractor=ip_extractor)
        def view(request):
            return JsonResponse({"ok": True})

        request = factory.get("/")
        for i in range(2):
            response = view(request)
            assert response.status_code == 200
            assert int(response.headers["X-RateLimit-Remaining"]) == 1 - i
        response = view(request)
        assert response.status_code == 429
        time.sleep(1.1)
        response = view(request)
        assert response.status_code == 200
        assert int(response.headers["X-RateLimit-Remaining"]) == 0  # full again

    def test_gcra_allows_within_burst(self, limiter_sync, factory):
        @rate_limit(limiter_sync, "gcra", key_extractor=ip_extractor)
        def view(request):
            return JsonResponse({"ok": True})

        request = factory.get("/")
        for i in range(4):
            response = view(request)
            assert response.status_code == 200
            assert int(response.headers["X-RateLimit-Remaining"]) == 3 - i
        response = view(request)
        assert response.status_code == 429
        time.sleep(0.6)  # refill one token
        response = view(request)
        assert response.status_code == 200
        assert int(response.headers["X-RateLimit-Remaining"]) == 0

    def test_composite_rules(self, limiter_sync, factory):
        @rate_limit(limiter_sync, ["global", "strict"], key_extractor=ip_extractor)
        def view(request):
            return JsonResponse({"ok": True})

        request = factory.get("/")
        # global limit=2, strict limit=1 → stricter is strict
        response = view(request)
        assert response.status_code == 200
        # remaining should be 0 (strict has limit=1, after 1 request remaining=0)
        assert int(response.headers["X-RateLimit-Remaining"]) == 0
        # second request denied
        response = view(request)
        assert response.status_code == 429

    def test_custom_key_extractor(self, limiter_sync, factory):
        @rate_limit(limiter_sync, "global", key_extractor=api_key_extractor)
        def view(request):
            return JsonResponse({"ok": True})

        request = factory.get("/", headers={"X-API-Key": "key1"})
        response = view(request)
        assert response.status_code == 200
        request2 = factory.get("/", headers={"X-API-Key": "key1"})
        response = view(request2)
        assert response.status_code == 200
        # Third with same key denied
        request3 = factory.get("/", headers={"X-API-Key": "key1"})
        response = view(request3)
        assert response.status_code == 429
        # Different key allowed
        request4 = factory.get("/", headers={"X-API-Key": "key2"})
        response = view(request4)
        assert response.status_code == 200

    def test_on_limit_callback(self, limiter_sync, factory):
        def custom_limit_response(request, result):
            return JsonResponse({"custom": "limited"}, status=429)

        @rate_limit(limiter_sync, "strict", key_extractor=ip_extractor, on_limit=custom_limit_response)
        def view(request):
            return JsonResponse({"ok": True})

        request = factory.get("/")
        response = view(request)
        assert response.status_code == 200
        response = view(request)
        assert response.status_code == 429
        assert json.loads(response.content) == {"custom": "limited"}

    def test_decorator_with_user_id_extractor(self, limiter_sync, factory):
        @rate_limit(limiter_sync, "global", key_extractor=user_id_extractor)
        def view(request):
            return JsonResponse({"ok": True})

        class User1:
            is_authenticated = True
            pk = 1
        class User2:
            is_authenticated = True
            pk = 2

        request1 = factory.get("/")
        request1.user = User1()
        request2 = factory.get("/")
        request2.user = User2()

        # User1: limit=2
        assert view(request1).status_code == 200
        assert view(request1).status_code == 200
        assert view(request1).status_code == 429

        # User2: fresh, still allowed
        assert view(request2).status_code == 200

# Tests for Async Decorator
class TestAsyncDecorator:
    @pytest.mark.asyncio
    async def test_async_view_with_sliding_window(self, limiter_async, factory):
        @rate_limit(limiter_async, "async_test", key_extractor=ip_extractor)
        async def view(request):
            return JsonResponse({"ok": True})

        request = factory.get("/")
        for i in range(2):
            response = await view(request)
            assert response.status_code == 200
            assert int(response.headers["X-RateLimit-Remaining"]) == 1 - i
        response = await view(request)
        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_async_view_with_composite(self, limiter_async):
        storage = AsyncMemoryStorage()
        rules = [LimitRule(name="a", algorithm="fixed_window", limit=1, window=10),
                 LimitRule(name="b", algorithm="fixed_window", limit=2, window=10)]
        limiter = AsyncRateLimiter(storage, rules)

        @rate_limit(limiter, ["a", "b"], key_extractor=ip_extractor)
        async def view(request):
            return JsonResponse({"ok": True})

        factory = RequestFactory()
        request = factory.get("/")
        response = await view(request)
        assert response.status_code == 200
        assert int(response.headers["X-RateLimit-Remaining"]) == 0  # from a (limit=1)
        response = await view(request)
        assert response.status_code == 429

# Tests for Middleware (Global)
class TestMiddleware:
    def test_middleware_allows_within_limit(self, limiter_sync, client):
        # Create middleware class
        Middleware = get_middleware_class(limiter_sync, "global", key_extractor=ip_extractor)

        # Apply middleware to a simple Django view
        def dummy_view(request):
            return JsonResponse({"ok": True})

        # simulate the middleware chain.
        def get_response(request):
            return dummy_view(request)

        middleware = Middleware(get_response)

        # Create requests
        factory = RequestFactory()
        for i in range(2):
            request = factory.get("/")
            response = middleware(request)
            assert response.status_code == 200
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers
            assert int(response.headers["X-RateLimit-Remaining"]) == 1 - i
        request = factory.get("/")
        response = middleware(request)
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    def test_middleware_with_custom_key_extractor(self, limiter_sync, client):
        Middleware = get_middleware_class(limiter_sync, "global", key_extractor=api_key_extractor)
        def dummy_view(request):
            return JsonResponse({"ok": True})
        def get_response(request):
            return dummy_view(request)
        middleware = Middleware(get_response)
        factory = RequestFactory()
        # First request with key1 allowed
        request = factory.get("/", headers={"X-API-Key": "key1"})
        response = middleware(request)
        assert response.status_code == 200
        # Second with key1 allowed (limit=2)
        request = factory.get("/", headers={"X-API-Key": "key1"})
        response = middleware(request)
        assert response.status_code == 200
        # Third with key1 denied
        request = factory.get("/", headers={"X-API-Key": "key1"})
        response = middleware(request)
        assert response.status_code == 429
        # key2 allowed
        request = factory.get("/", headers={"X-API-Key": "key2"})
        response = middleware(request)
        assert response.status_code == 200

    def test_middleware_returns_429_with_headers(self, limiter_sync, client):
        Middleware = get_middleware_class(limiter_sync, "strict", key_extractor=ip_extractor)
        def dummy_view(request):
            return JsonResponse({"ok": True})
        def get_response(request):
            return dummy_view(request)
        middleware = Middleware(get_response)
        factory = RequestFactory()
        request = factory.get("/")
        response = middleware(request)
        assert response.status_code == 200
        response = middleware(request)  # strict limit=1, so second denied
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        # Headers from the middleware (X-RateLimit-*) should be present on 429
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    def test_middleware_with_user_id_extractor(self, limiter_sync):
        Middleware = get_middleware_class(limiter_sync, "global", key_extractor=user_id_extractor)
        def dummy_view(request):
            return JsonResponse({"ok": True})
        def get_response(request):
            return dummy_view(request)
        middleware = Middleware(get_response)
        factory = RequestFactory()

        class User1:
            is_authenticated = True
            pk = 1
        class User2:
            is_authenticated = True
            pk = 2

        request1 = factory.get("/")
        request1.user = User1() # type: ignore
        request2 = factory.get("/")
        request2.user = User2() # type: ignore

        # User1: limit=2
        assert middleware(request1).status_code == 200
        assert middleware(request1).status_code == 200
        assert middleware(request1).status_code == 429

        # User2: still allowed
        assert middleware(request2).status_code == 200

class TestExtractors:
    def test_ip_extractor_returns_ip(self, factory):
        request = factory.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8")
        assert ip_extractor(request) == "1.2.3.4"
        # without forwarded
        request = factory.get("/", REMOTE_ADDR="9.8.7.6")
        assert ip_extractor(request) == "9.8.7.6"

    def test_user_id_extractor_authenticated(self, factory):
        class MockUser:
            is_authenticated = True
            pk = 123
        request = factory.get("/")
        request.user = MockUser()
        assert user_id_extractor(request) == "123"

    def test_user_id_extractor_anonymous(self, factory):
        class MockUser:
            is_authenticated = False
        request = factory.get("/")
        request.user = MockUser()
        assert user_id_extractor(request) == "anon"

    def test_api_key_extractor(self, factory):
        request = factory.get("/", HTTP_X_API_KEY="secret-key")
        assert api_key_extractor(request) == "secret-key"
        # default header name
        request = factory.get("/", HTTP_AUTHORIZATION="Bearer token")  # not used
        assert api_key_extractor(request) == ""  # returns empty

# Edge Cases
def test_missing_rule_raises_value_error(limiter_sync, factory):
    @rate_limit(limiter_sync, "missing", key_extractor=ip_extractor)
    def view(request):
        return JsonResponse({"ok": True})

    request = factory.get("/")
    with pytest.raises(ValueError, match="Rule 'missing' not found"):
        view(request)

def test_invalid_limiter_type():
    # Cannot mix async limiter with sync view (raises TypeError)
    storage = AsyncMemoryStorage()
    rules = [LimitRule(name="test", algorithm="fixed_window", limit=10, window=60)]
    limiter = AsyncRateLimiter(storage, rules)  # async
    with pytest.raises(TypeError, match="Sync view requires a sync"):
        @rate_limit(limiter, "test", key_extractor=ip_extractor)
        def sync_view(request):
            return JsonResponse({"ok": True})

def test_async_limiter_with_async_view_works(limiter_async, factory):
    @rate_limit(limiter_async, "async_test", key_extractor=ip_extractor)
    async def view(request):
        return JsonResponse({"ok": True})
    request = factory.get("/")
    import asyncio
    response = asyncio.run(view(request))
    assert response.status_code == 200

def test_anonymous_user_fallback(limiter_sync, factory):
    @rate_limit(limiter_sync, "global", key_extractor=user_id_extractor)
    def view(request):
        return JsonResponse({"ok": True})

    class AnonUser:
        is_authenticated = False
    request = factory.get("/")
    request.user = AnonUser()
    # All anonymous requests share the same key "anonymous"
    assert view(request).status_code == 200
    assert view(request).status_code == 200
    assert view(request).status_code == 429

def test_composite_with_user_extractor(limiter_sync, factory):
    @rate_limit(limiter_sync, ["global", "strict"], key_extractor=user_id_extractor)
    def view(request):
        return JsonResponse({"ok": True})

    class User1:
        is_authenticated = True
        pk = 1
    request = factory.get("/")
    request.user = User1()
    # strict limit=1 => first allowed, second denied
    assert view(request).status_code == 200
    assert view(request).status_code == 429
    # different user => allowed
    class User2:
        is_authenticated = True
        pk = 2
    request2 = factory.get("/")
    request2.user = User2()
    assert view(request2).status_code == 200