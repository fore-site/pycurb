import pytest
from pydantic import ValidationError
from pycurb.core.models import LimitRule, RateLimitResult, RateLimitHeaders
import time


class TestLimitRule:
    """Test the LimitRule configuration model."""

    def test_valid_sliding_window(self):
        rule = LimitRule(
            name="test", algorithm="sliding_window", limit=100, window=60
        )
        assert rule.name == "test"
        assert rule.algorithm == "sliding_window"
        assert rule.limit == 100
        assert rule.window == 60
        assert rule.capacity is None
        assert rule.refill_rate is None
        assert rule.leak_rate is None

    def test_valid_fixed_window(self):
        rule = LimitRule(name="fixed", algorithm="fixed_window", limit=50, window=120)
        assert rule.algorithm == "fixed_window"

    def test_valid_token_bucket_with_capacity_refill(self):
        rule = LimitRule(
            name="tb", algorithm="token_bucket", capacity=200, refill_rate=10.0
        )
        assert rule.capacity == 200
        assert rule.refill_rate == 10.0
        # limit and window should be None
        assert rule.limit is None
        assert rule.window is None

    def test_valid_token_bucket_with_limit_window_fallback(self):
        rule = LimitRule(
            name="tb_fallback", algorithm="token_bucket", limit=100, window=60
        )
        # capacity and refill_rate are derived, but not stored
        assert rule.limit == 100
        assert rule.window == 60
        assert rule.capacity is None
        assert rule.refill_rate is None

    def test_valid_token_bucket_mixed(self):
        # provide capacity but use window for refill_rate
        rule = LimitRule(
            name="mixed", algorithm="token_bucket", capacity=500, window=10
        )
        assert rule.capacity == 500
        assert rule.window == 10
        assert rule.refill_rate is None  # will be computed as 50

    def test_valid_leaky_bucket(self):
        rule = LimitRule(
            name="leaky", algorithm="leaky_bucket", capacity=100, leak_rate=5.0
        )
        assert rule.capacity == 100
        assert rule.leak_rate == 5.0

    def test_leaky_bucket_fallback_limit(self):
        rule = LimitRule(
            name="leaky_limit", algorithm="leaky_bucket", limit=200, leak_rate=10.0
        )
        assert rule.limit == 200
        assert rule.leak_rate == 10.0

    # Validation errors

    def test_sliding_window_missing_limit(self):
        with pytest.raises(ValidationError) as exc:
            LimitRule(name="bad", algorithm="sliding_window", window=60)
        assert "limit" in str(exc.value).lower()

    def test_sliding_window_missing_window(self):
        with pytest.raises(ValidationError) as exc:
            LimitRule(name="bad", algorithm="sliding_window", limit=100)
        assert "window" in str(exc.value).lower()

    def test_token_bucket_missing_capacity_and_limit(self):
        with pytest.raises(ValidationError) as exc:
            LimitRule(name="bad", algorithm="token_bucket", refill_rate=10)
        assert "'capacity' or 'limit'" in str(exc.value).lower()

    def test_token_bucket_missing_refill_and_window(self):
        with pytest.raises(ValidationError) as exc:
            LimitRule(name="bad", algorithm="token_bucket", capacity=100)
        assert "'refill_rate' or 'window'" in str(exc.value).lower()

    def test_token_bucket_invalid_refill_rate_zero(self):
        # zero not allowed by field constraint (gt=0)
        with pytest.raises(ValidationError):
            LimitRule(name="bad", algorithm="token_bucket", capacity=100, refill_rate=0)

    def test_leaky_bucket_missing_capacity_and_limit(self):
        with pytest.raises(ValidationError) as exc:
            LimitRule(name="bad", algorithm="leaky_bucket", leak_rate=5)
        assert "'capacity' or 'limit'" in str(exc.value).lower()

    def test_leaky_bucket_missing_leak_rate(self):
        with pytest.raises(ValidationError) as exc:
            LimitRule(name="bad", algorithm="leaky_bucket", capacity=100)
        assert "leak_rate" in str(exc.value).lower()

    def test_field_positive_constraints(self):
        with pytest.raises(ValidationError):
            LimitRule(name="bad", algorithm="fixed_window", limit=0, window=60)
        with pytest.raises(ValidationError):
            LimitRule(name="bad", algorithm="fixed_window", limit=100, window=0)

    def test_metadata_any_type(self):
        rule = LimitRule(
            name="meta",
            algorithm="fixed_window",
            limit=10,
            window=1,
            metadata={"priority": "high", "tier": 3},
        )
        assert rule.metadata["priority"] == "high"

    def test_immutability(self):
        rule = LimitRule(name="immutable", algorithm="fixed_window", limit=10, window=1)
        with pytest.raises(ValidationError):
            rule.limit = 20  # frozen=True prevents mutation

    def test_valid_gcra_with_capacity_refill(self):
        rule = LimitRule(name="gcra1", algorithm="gcra", capacity=100, refill_rate=5.0)
        assert rule.capacity == 100
        assert rule.refill_rate == 5.0

    def test_valid_gcra_with_limit_refill(self):
        rule = LimitRule(name="gcra2", algorithm="gcra", limit=200, refill_rate=10.0)
        assert rule.limit == 200
        assert rule.refill_rate == 10.0

    def test_gcra_missing_capacity_and_limit(self):
        with pytest.raises(ValidationError) as exc:
            LimitRule(name="bad", algorithm="gcra", refill_rate=5)
        assert "'capacity' or 'limit'" in str(exc.value).lower()

    def test_gcra_missing_refill_rate(self):
        with pytest.raises(ValidationError) as exc:
            LimitRule(name="bad", algorithm="gcra", capacity=100)
        assert "refill_rate" in str(exc.value).lower()

    def test_gcra_invalid_refill_rate_zero(self):
        with pytest.raises(ValidationError):
            LimitRule(name="bad", algorithm="gcra", capacity=100, refill_rate=0)


class TestRateLimitResult:
    def test_valid_allowed(self):
        result = RateLimitResult(
            allowed=True, remaining=99, reset_at=1734567890.5, limit=100
        )
        assert result.allowed is True
        assert result.remaining == 99

    def test_valid_denied_with_retry_after(self):
        result = RateLimitResult(
            allowed=False, remaining=0, reset_at=1734567890.5, limit=100, retry_after=42
        )
        assert result.retry_after == 42

    def test_negative_remaining_not_allowed(self):
        with pytest.raises(ValidationError):
            RateLimitResult(allowed=True, remaining=-1, reset_at=1, limit=10)

    def test_immutable(self):
        result = RateLimitResult(allowed=True, remaining=5, reset_at=123, limit=10)
        with pytest.raises(ValidationError):
            result.remaining = 4


class TestRateLimitHeaders:
    def test_to_dict(self):
        headers = RateLimitHeaders(limit=100, remaining=50, reset=1234567890)
        d = headers.to_dict()
        assert d["X-RateLimit-Limit"] == "100"
        assert d["X-RateLimit-Remaining"] == "50"
        assert d["X-RateLimit-Reset"] == "1234567890"
        assert "Retry-After" not in d

    def test_to_dict_with_retry_after(self):
        headers = RateLimitHeaders(
            limit=100, remaining=0, reset=1234567890, retry_after=30
        )
        d = headers.to_dict()
        assert d["Retry-After"] == "30"

    def test_from_result_with_allowed(self):
        result = RateLimitResult(
            allowed=True, remaining=80, reset_at=1734567890.5, limit=100
        )
        headers = RateLimitHeaders.from_result(result)
        assert headers.limit == 100
        assert headers.remaining == 80
        assert headers.reset == 1734567890
        assert headers.retry_after is None

    def test_from_result_denied_without_retry_after(self):
        result = RateLimitResult(
            allowed=False,
            remaining=0,
            reset_at=time.time() + 30,  # 30 seconds from now
            limit=100,
        )
        headers = RateLimitHeaders.from_result(result)
        # retry_after should be computed as ~30
        assert headers.retry_after is not None
        assert 28 <= headers.retry_after <= 32

    def test_from_result_denied_with_explicit_retry_after(self):
        result = RateLimitResult(
            allowed=False,
            remaining=0,
            reset_at=time.time() + 30,
            limit=100,
            retry_after=15,  # explicit overrides computed
        )
        headers = RateLimitHeaders.from_result(result)
        assert headers.retry_after == 15

    def test_from_result_now_override(self):
        result = RateLimitResult(allowed=False, remaining=0, reset_at=1000, limit=100)
        # Provide a fixed "now" timestamp
        headers = RateLimitHeaders.from_result(result, now=950)
        assert headers.retry_after == 50  # 1000 - 950
