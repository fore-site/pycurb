import pytest
from flask import Flask, jsonify
from pycurb.core import RateLimiter, MemoryStorage, LimitRule
from pycurb.adapters.flask import rate_limit, RateLimit, ip_extractor, api_key_extractor
import time


# Fixtures
@pytest.fixture
def limiter():
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
def app(limiter):
    app = Flask(__name__)

    @app.route("/")
    def home():
        return jsonify({"ok": True})

    @app.route("/strict")
    @rate_limit(limiter, "strict", key_extractor=ip_extractor)
    def strict():
        return jsonify({"ok": True})

    @app.route("/composite")
    @rate_limit(limiter, ["global", "strict"], key_extractor=ip_extractor)
    def composite():
        return jsonify({"ok": True})

    @app.route("/burst")
    @rate_limit(limiter, "burst", key_extractor=ip_extractor)
    def burst():
        return jsonify({"ok": True})

    return app


@pytest.fixture
def client(app):
    return app.test_client()


# Tests
class TestDecorator:
    def test_sliding_window_allows_within_limit(self, limiter):
        app = Flask(__name__)

        @app.route("/sliding")
        @rate_limit(limiter, "sliding", key_extractor=ip_extractor)
        def sliding():
            return jsonify({"ok": True})

        client = app.test_client()
        for i in range(5):
            resp = client.get("/sliding")
            assert resp.status_code == 200
            assert "X-RateLimit-Remaining" in resp.headers
            assert int(resp.headers["X-RateLimit-Remaining"]) == 4 - i
        resp = client.get("/sliding")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_fixed_window_allows_within_limit(self, limiter):
        app = Flask(__name__)

        @app.route("/fixed")
        @rate_limit(limiter, "fixed", key_extractor=ip_extractor)
        def fixed():
            return jsonify({"ok": True})

        client = app.test_client()
        for i in range(3):
            resp = client.get("/fixed")
            assert resp.status_code == 200
            assert int(resp.headers["X-RateLimit-Remaining"]) == 2 - i
        resp = client.get("/fixed")
        assert resp.status_code == 429

    def test_token_bucket_allows_burst_then_refills(self, limiter):
        app = Flask(__name__)

        @app.route("/burst")
        @rate_limit(limiter, "burst", key_extractor=ip_extractor)
        def burst():
            return jsonify({"ok": True})

        client = app.test_client()
        for i in range(3):
            resp = client.get("/burst")
            assert resp.status_code == 200
            assert int(resp.headers["X-RateLimit-Remaining"]) == 2 - i
        resp = client.get("/burst")
        assert resp.status_code == 429
        time.sleep(1.1)
        resp = client.get("/burst")
        assert resp.status_code == 200
        assert int(resp.headers["X-RateLimit-Remaining"]) == 0  # consumed

    def test_leaky_bucket_allows_within_capacity(self, limiter):
        app = Flask(__name__)

        @app.route("/leaky")
        @rate_limit(limiter, "leaky", key_extractor=ip_extractor)
        def leaky():
            return jsonify({"ok": True})

        client = app.test_client()
        for i in range(2):
            resp = client.get("/leaky")
            assert resp.status_code == 200
            assert int(resp.headers["X-RateLimit-Remaining"]) == 1 - i
        resp = client.get("/leaky")
        assert resp.status_code == 429
        time.sleep(1.1)
        resp = client.get("/leaky")
        assert resp.status_code == 200

    def test_gcra_allows_within_burst(self, limiter):
        app = Flask(__name__)

        @app.route("/gcra")
        @rate_limit(limiter, "gcra", key_extractor=ip_extractor)
        def gcra():
            return jsonify({"ok": True})

        client = app.test_client()
        for i in range(4):
            resp = client.get("/gcra")
            assert resp.status_code == 200
            assert int(resp.headers["X-RateLimit-Remaining"]) == 3 - i
        resp = client.get("/gcra")
        assert resp.status_code == 429
        time.sleep(0.6)
        resp = client.get("/gcra")
        assert resp.status_code == 200
        assert int(resp.headers["X-RateLimit-Remaining"]) == 0

    def test_composite_rules(self, limiter):
        app = Flask(__name__)

        @app.route("/composite")
        @rate_limit(limiter, ["global", "strict"], key_extractor=ip_extractor)
        def composite():
            return jsonify({"ok": True})

        client = app.test_client()
        resp = client.get("/composite")
        assert resp.status_code == 200
        assert int(resp.headers["X-RateLimit-Remaining"]) == 0  # strict limit=1
        resp = client.get("/composite")
        assert resp.status_code == 429

    def test_custom_key_extractor(self, limiter):
        app = Flask(__name__)

        @app.route("/api")
        @rate_limit(limiter, "global", key_extractor=api_key_extractor)
        def api():
            return jsonify({"ok": True})

        client = app.test_client()
        headers = {"X-API-Key": "key1"}
        resp1 = client.get("/api", headers=headers)
        assert resp1.status_code == 200
        resp2 = client.get("/api", headers=headers)
        assert resp2.status_code == 200
        resp3 = client.get("/api", headers=headers)
        assert resp3.status_code == 429
        headers2 = {"X-API-Key": "key2"}
        resp4 = client.get("/api", headers=headers2)
        assert resp4.status_code == 200

    def test_on_limit_callback(self, limiter):
        def custom_limit(result):
            return jsonify({"custom": "limited"}), 429

        app = Flask(__name__)

        @app.route("/")
        @rate_limit(
            limiter, "strict", key_extractor=ip_extractor, on_limit=custom_limit
        )
        def view():
            return jsonify({"ok": True})

        client = app.test_client()
        resp = client.get("/")
        assert resp.status_code == 200
        resp = client.get("/")
        assert resp.status_code == 429
        assert resp.json == {"custom": "limited"}


# Middleware Tests


class TestMiddleware:
    def test_global_rate_limit_allows_within_limit(self, limiter):
        app = Flask(__name__)
        RateLimit(app, limiter, "global", ip_extractor)

        @app.route("/")
        def home():
            return jsonify({"ok": True})

        client = app.test_client()
        for i in range(2):
            resp = client.get("/")
            assert resp.status_code == 200
            assert int(resp.headers["X-RateLimit-Remaining"]) == 1 - i
        resp = client.get("/")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_global_with_custom_key_extractor(self, limiter):
        app = Flask(__name__)
        RateLimit(app, limiter, "global", key_extractor=api_key_extractor)

        @app.route("/")
        def home():
            return jsonify({"ok": True})

        client = app.test_client()
        headers = {"X-API-Key": "key1"}
        for i in range(2):
            resp = client.get("/", headers=headers)
            assert resp.status_code == 200
        resp = client.get("/", headers=headers)
        assert resp.status_code == 429
        resp2 = client.get("/", headers={"X-API-Key": "key2"})
        assert resp2.status_code == 200

    def test_middleware_does_not_affect_other_routes(self, limiter):
        # Since middleware is global, it affects all routes.
        # test that a route with no decorator still gets limited.
        app = Flask(__name__)
        RateLimit(app, limiter, "strict", ip_extractor)

        @app.route("/")
        def home():
            return jsonify({"ok": True})

        client = app.test_client()
        resp = client.get("/")
        assert resp.status_code == 200
        resp = client.get("/")
        assert resp.status_code == 429


# Edge Cases
def test_missing_rule_raises_error(limiter):
    app = Flask(__name__)

    @app.route("/")
    @rate_limit(limiter, "missing", key_extractor=ip_extractor)
    def view():
        return jsonify({"ok": True})

    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 500
