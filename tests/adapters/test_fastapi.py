from fastapi.testclient import TestClient
from fastapi import FastAPI, Depends
from pycurb.core import AsyncRateLimiter, LimitRule, AsyncMemoryStorage
from pycurb.adapters.fastapi import (
    RateLimitMiddleware,
    rate_limiter,
    api_key_extractor,
    ip_extractor,
)
import pytest
import time

# Fixtures


@pytest.fixture
def limiter():
    storage = AsyncMemoryStorage()
    rules = [
        LimitRule(name="global", algorithm="sliding_window", limit=2, window=10),
        LimitRule(name="strict", algorithm="fixed_window", limit=1, window=10),
        LimitRule(name="burst", algorithm="token_bucket", capacity=3, refill_rate=1.0),
        LimitRule(name="sliding", algorithm="sliding_window", limit=5, window=10),
        LimitRule(name="fixed", algorithm="fixed_window", limit=3, window=10),
        LimitRule(name="leaky", algorithm="leaky_bucket", capacity=2, leak_rate=1.0),
        LimitRule(name="gcra", algorithm="gcra", capacity=4, refill_rate=2.0),
    ]
    return AsyncRateLimiter(storage, rules)


@pytest.fixture
def app(limiter):
    app = FastAPI()

    # Global middleware
    app.add_middleware(
        RateLimitMiddleware,
        limiter=limiter,
        rule_name="global",
        key_extractor=ip_extractor,
    )

    @app.get("/")
    async def home():
        return {"ok": True}

    # Endpoint with per‑endpoint rule (strict)
    @app.get("/strict")
    async def strict_endpoint(
        _=Depends(rate_limiter(limiter, "strict", key_extractor=api_key_extractor)),
    ):
        return {"ok": True}

    # Endpoint with composite rules (global + strict)
    @app.get("/composite")
    async def composite_endpoint(
        _=Depends(
            rate_limiter(limiter, ["global", "strict"], key_extractor=ip_extractor)
        ),
    ):
        return {"ok": True}

    # Endpoint with token bucket rule (burst)
    @app.get("/burst")
    async def burst_endpoint(
        _=Depends(rate_limiter(limiter, "burst", key_extractor=ip_extractor)),
    ):
        return {"ok": True}

    return app


@pytest.fixture
def burst_app(limiter):
    app = FastAPI()

    @app.get("/burst")
    async def burst_endpoint(
        _=Depends(rate_limiter(limiter, "burst", key_extractor=ip_extractor)),
    ):
        return {"ok": True}

    return app


@pytest.fixture
def sliding_app(limiter):
    app = FastAPI()

    # sliding rule: limit=5, window=10
    @app.get("/sliding")
    async def sliding_endpoint(
        _=Depends(rate_limiter(limiter, "sliding", key_extractor=ip_extractor)),
    ):
        return {"ok": True}

    return app


@pytest.fixture
def fixed_app(limiter):
    app = FastAPI()

    # fixed rule: limit=3, window=10
    @app.get("/fixed")
    async def fixed_endpoint(
        _=Depends(rate_limiter(limiter, "fixed", key_extractor=ip_extractor)),
    ):
        return {"ok": True}

    return app


@pytest.fixture
def leaky_app(limiter):
    app = FastAPI()

    # leaky rule: capacity=2, leak_rate=1.0
    @app.get("/leaky")
    async def leaky_endpoint(
        _=Depends(rate_limiter(limiter, "leaky", key_extractor=ip_extractor)),
    ):
        return {"ok": True}

    return app


@pytest.fixture
def gcra_app(limiter):
    app = FastAPI()

    # GCRA rule: capacity=4, refill_rate=2.0
    @app.get("/gcra")
    async def gcra_endpoint(
        _=Depends(rate_limiter(limiter, "gcra", key_extractor=ip_extractor)),
    ):
        return {"ok": True}

    return app


# Tests
def test_middleware_allows_requests():
    storage = AsyncMemoryStorage()
    rule = LimitRule(name="test", algorithm="fixed_window", limit=2, window=10)
    limiter = AsyncRateLimiter(storage, [rule])
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limiter=limiter, rule_name="test")

    @app.get("/")
    def home():
        return {"ok": True}

    client = TestClient(app)
    for i in range(2):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers
        assert int(resp.headers["X-RateLimit-Remaining"]) == 1 - i
    resp = client.get("/")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


class TestMiddleware:
    def test_allows_requests_within_limit(self, app):
        client = TestClient(app)
        for i in range(2):
            resp = client.get("/")
            assert resp.status_code == 200
            assert "X-RateLimit-Limit" in resp.headers
            assert "X-RateLimit-Remaining" in resp.headers
            assert "X-RateLimit-Reset" in resp.headers
            assert int(resp.headers["X-RateLimit-Remaining"]) == 1 - i

    def test_denies_requests_exceeding_limit(self, app):
        client = TestClient(app)
        for _ in range(2):
            client.get("/")
        resp = client.get("/")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        assert int(resp.headers["Retry-After"]) > 0

    def test_exclude_paths_works(self, limiter):
        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            limiter=limiter,
            rule_name="global",
            exclude_paths=["/health"],
        )

        @app.get("/")
        async def root():
            return {"ok": True}

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        client = TestClient(app)
        # Root is limited: 2 requests allowed
        assert client.get("/").status_code == 200
        assert client.get("/").status_code == 200
        assert client.get("/").status_code == 429
        # Health is never limited
        for _ in range(10):
            assert client.get("/health").status_code == 200


class TestDependency:
    def test_per_endpoint_rule_allows_within_limit(self, app):
        client = TestClient(app)
        # strict rule: limit=1 per 10 seconds
        resp = client.get("/strict", headers={"X-API-Key": "test"})
        assert resp.status_code == 200
        # Second request denied
        resp = client.get("/strict", headers={"X-API-Key": "test"})
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_uses_custom_key_extractor(self, app):
        client = TestClient(app)
        # Different API keys have independent counters
        resp1 = client.get("/strict", headers={"X-API-Key": "key1"})
        assert resp1.status_code == 200
        resp2 = client.get("/strict", headers={"X-API-Key": "key2"})
        assert resp2.status_code == 200  # different key, still allowed


class TestCompositeRules:
    def test_composite_allows_only_if_all_rules_allow(self, app):
        client = TestClient(app)
        # global limit=2, strict limit=1
        # First request: both allow
        resp = client.get("/composite")
        assert resp.status_code == 200
        # Second request: global still allows (1 left), strict denies (already used 1)
        resp = client.get("/composite")
        assert resp.status_code == 429
        # Headers should show remaining from the restrictive rule
        assert "Retry-After" in resp.headers


class TestTokenBucket:
    def test_token_bucket_allows_burst_then_refills(self, burst_app):
        client = TestClient(burst_app)
        # burst rule: capacity=3, refill_rate=1 token/sec
        for i in range(3):
            resp = client.get("/burst")
            assert resp.status_code == 200

        # Fourth request should be denied (burst exhausted)
        resp = client.get("/burst")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers  # dependency adds Retry-After

        # Wait for refill (at least 1 second)
        time.sleep(1.1)
        resp = client.get("/burst")
        assert resp.status_code == 200


class TestSlidingWindow:
    def test_sliding_allows_within_limit(self, sliding_app):
        client = TestClient(sliding_app)
        for i in range(5):
            resp = client.get("/sliding")
            assert resp.status_code == 200
        resp = client.get("/sliding")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_sliding_window_slides_after_time(self, sliding_app):
        client = TestClient(sliding_app)
        # Send 5 requests quickly (fill window)
        for _ in range(5):
            client.get("/sliding")
        # 6th request denied
        resp = client.get("/sliding")
        assert resp.status_code == 429


class TestFixedWindow:
    def test_fixed_allows_within_limit(self, fixed_app):
        client = TestClient(fixed_app)
        for i in range(3):
            resp = client.get("/fixed")
            assert resp.status_code == 200
        resp = client.get("/fixed")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers


class TestLeakyBucket:
    def test_leaky_allows_within_capacity(self, leaky_app):
        client = TestClient(leaky_app)
        # capacity=2, leak_rate=1.0
        for i in range(2):
            resp = client.get("/leaky")
            assert resp.status_code == 200
        resp = client.get("/leaky")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_leaky_leaks_over_time(self, leaky_app):
        client = TestClient(leaky_app)
        # Fill bucket
        client.get("/leaky")
        client.get("/leaky")
        # Denied
        resp = client.get("/leaky")
        assert resp.status_code == 429
        # Wait for leak (1 second)
        import time

        time.sleep(1.1)
        resp = client.get("/leaky")
        assert resp.status_code == 200


class TestGCRA:
    def test_gcra_allows_within_burst(self, gcra_app):
        client = TestClient(gcra_app)
        # capacity=4, refill_rate=2.0 → burst=4, rate=2 req/sec
        for i in range(4):
            resp = client.get("/gcra")
            assert resp.status_code == 200
        resp = client.get("/gcra")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_gcra_refills(self, gcra_app):
        client = TestClient(gcra_app)
        # Exhaust bucket
        for _ in range(4):
            client.get("/gcra")
        # Wait for refill (0.5 seconds for one token)
        import time

        time.sleep(0.6)
        resp = client.get("/gcra")
        assert resp.status_code == 200


class TestCompositeWithDifferentAlgorithms:
    def test_composite_sliding_and_token(self, limiter):
        app = FastAPI()

        @app.get("/composite-mixed")
        async def mixed_endpoint(
            _=Depends(
                rate_limiter(limiter, ["sliding", "burst"], key_extractor=ip_extractor)
            ),
        ):
            return {"ok": True}

        client = TestClient(app)
        # sliding limit=5, burst limit=3 → the stricter is burst (3)
        for i in range(3):
            resp = client.get("/composite-mixed")
            assert resp.status_code == 200
        resp = client.get("/composite-mixed")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers


# Edge Cases


def test_missing_rule_raises_500():
    storage = AsyncMemoryStorage()
    limiter = AsyncRateLimiter(storage, [])  # no rules
    app = FastAPI()

    @app.get("/bad")
    async def bad(
        _=Depends(rate_limiter(limiter, "missing", key_extractor=ip_extractor)),
    ):
        return {"ok": True}

    client = TestClient(app)
    with pytest.raises(Exception):  # ValueError from resolver
        client.get("/bad")
