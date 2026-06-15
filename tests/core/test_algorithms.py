import pytest

from pycurb.core.algorithms import (
    FixedWindowAlgorithm,
    AsyncFixedWindowAlgorithm,
    LeakyBucketAlgorithm,
    AsyncLeakyBucketAlgorithm,
    SlidingWindowAlgorithm,
    AsyncSlidingWindowAlgorithm,
    TokenBucketAlgorithm,
    AsyncTokenBucketAlgorithm,
    GcraAlgorithm,
    AsyncGcraAlgorithm,
)
from pycurb.core.algorithms import fixed_window_async as fixed_window_module
from pycurb.core.algorithms import fixed_window as fixed_window_sync_module
from pycurb.core.algorithms import leaky_bucket_async as leaky_bucket_module
from pycurb.core.algorithms import leaky_bucket as leaky_bucket_sync_module
from pycurb.core.algorithms import sliding_window_async as sliding_window_module
from pycurb.core.algorithms import sliding_window as sliding_window_sync_module
from pycurb.core.algorithms import token_bucket_async as token_bucket_module
from pycurb.core.algorithms import token_bucket as token_bucket_sync_module
from pycurb.core.algorithms import gcra_async as gcra_module
from pycurb.core.algorithms import gcra as gcra_sync_module
from pycurb.core.models import LimitRule, RateLimitResult


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
    async def gcra(self, **kwargs):
        self.calls.append(("gcra", kwargs))
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
    def gcra(self, **kwargs):
        self.calls.append(("gcra", kwargs))
        return self.response


def freeze_time(monkeypatch, module):
    monkeypatch.setattr(module.time, "time", lambda: BASE_TIME)


def assert_result(result, *, allowed=True, remaining=4, reset_at=RESET_AT, limit, rule_name):
    assert isinstance(result, RateLimitResult)
    assert result.allowed is allowed
    assert result.remaining == remaining
    assert result.reset_at == pytest.approx(reset_at)
    assert result.limit == limit
    assert result.retry_after is None
    assert result.rule_name == rule_name


def _prefixed_expected(expected_kwargs, rule):
    """Return a copy of expected_kwargs with the key prefixed by the rule name."""
    expected = expected_kwargs.copy()
    if "key" in expected:
        expected["key"] = f"{rule.name}:{expected["key"]}"
    return expected


class TestAsyncAlgorithms:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("algorithm", "module", "rule", "storage_method", "expected_kwargs"),
        [
            (
                AsyncSlidingWindowAlgorithm(),
                sliding_window_module,
                LimitRule(name="sw", algorithm="sliding_window", limit=5, window=60),
                "sliding_window",
                {"key": "client:1", "limit": 5, "window": 60, "now": BASE_TIME},
            ),
            (
                AsyncFixedWindowAlgorithm(),
                fixed_window_module,
                LimitRule(name="fw", algorithm="fixed_window", limit=10, window=30),
                "fixed_window",
                {"key": "client:1", "limit": 10, "window": 30, "now": BASE_TIME},
            ),
            (
                AsyncTokenBucketAlgorithm(),
                token_bucket_module,
                LimitRule(name="tb", algorithm="token_bucket", capacity=7, refill_rate=2.5),
                "token_bucket",
                {"key": "client:1", "capacity": 7, "refill_rate": 2.5, "now": BASE_TIME},
            ),
            (
                AsyncLeakyBucketAlgorithm(),
                leaky_bucket_module,
                LimitRule(name="lb", algorithm="leaky_bucket", capacity=3, leak_rate=0.75),
                "leaky_bucket",
                {"key": "client:1", "capacity": 3, "leak_rate": 0.75, "now": BASE_TIME},
            ),
            (
                AsyncGcraAlgorithm(),
                gcra_module,
                LimitRule(name="gcra", algorithm="gcra", capacity=7, refill_rate=2.5),
                "gcra",
                {"key": "client:1", "capacity": 7, "rate": 2.5, "now": BASE_TIME},
            ),
        ],
    )
    async def test_check_calls_expected_storage_method_and_wraps_result(
        self, monkeypatch, algorithm, module, rule, storage_method, expected_kwargs
    ):
        freeze_time(monkeypatch, module)
        storage = AsyncSpyStorage(response=(True, 4, RESET_AT))

        result = await algorithm.check("client:1", rule, storage)  # type: ignore[arg-type]

        assert storage.calls == [(storage_method, _prefixed_expected(expected_kwargs, rule))]
        assert_result(result, limit=expected_kwargs.get("limit", expected_kwargs.get("capacity")), rule_name=rule.name)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("algorithm", "module", "rule", "expected_limit"),
        [
            (
                AsyncSlidingWindowAlgorithm(),
                sliding_window_module,
                LimitRule(name="sw_denied", algorithm="sliding_window", limit=2, window=60),
                2,
            ),
            (
                AsyncFixedWindowAlgorithm(),
                fixed_window_module,
                LimitRule(name="fw_denied", algorithm="fixed_window", limit=2, window=60),
                2,
            ),
            (
                AsyncTokenBucketAlgorithm(),
                token_bucket_module,
                LimitRule(name="tb_denied", algorithm="token_bucket", capacity=2, refill_rate=1),
                2,
            ),
            (
                AsyncLeakyBucketAlgorithm(),
                leaky_bucket_module,
                LimitRule(name="lb_denied", algorithm="leaky_bucket", capacity=2, leak_rate=1),
                2,
            ),
        ],
    )
    async def test_denied_storage_decision_is_preserved(self, monkeypatch, algorithm, module, rule, expected_limit):
        freeze_time(monkeypatch, module)
        storage = AsyncSpyStorage(response=(False, 0, RESET_AT))

        result = await algorithm.check("client:denied", rule, storage)  # type: ignore[arg-type]

        assert_result(result, allowed=False, remaining=0, limit=expected_limit, rule_name=rule.name)

    @pytest.mark.asyncio
    async def test_token_bucket_uses_limit_as_capacity_fallback(self, monkeypatch):
        freeze_time(monkeypatch, token_bucket_module)
        rule = LimitRule(name="tb_limit", algorithm="token_bucket", limit=12, refill_rate=3)
        storage = AsyncSpyStorage()

        result = await AsyncTokenBucketAlgorithm().check("client:tb", rule, storage)  # type: ignore[arg-type]

        assert storage.calls == [
            ("token_bucket", {"key": f"{rule.name}:client:tb", "capacity": 12, "refill_rate": 3, "now": BASE_TIME})
        ]
        assert_result(result, limit=12, rule_name="tb_limit")

    @pytest.mark.asyncio
    async def test_gcra_uses_limit_as_capacity_fallback(self, monkeypatch):
        freeze_time(monkeypatch, gcra_module)
        rule = LimitRule(name="gcra_limit", algorithm="gcra", limit=12, refill_rate=3)
        storage = AsyncSpyStorage()

        result = await AsyncGcraAlgorithm().check("client:gcra", rule, storage)  # type: ignore[arg-type]

        assert storage.calls == [
            ("gcra", {"key": f"{rule.name}:client:gcra", "capacity": 12, "rate": 3, "now": BASE_TIME})
        ]
        assert_result(result, limit=12, rule_name="gcra_limit")

    @pytest.mark.asyncio
    async def test_token_bucket_derives_refill_rate_from_capacity_and_window(self, monkeypatch):
        freeze_time(monkeypatch, token_bucket_module)
        rule = LimitRule(name="tb_window", algorithm="token_bucket", capacity=20, window=4)
        storage = AsyncSpyStorage()

        await AsyncTokenBucketAlgorithm().check("client:tb-window", rule, storage)  # type: ignore[arg-type]

        assert storage.calls == [
            ("token_bucket", {"key": f"{rule.name}:client:tb-window", "capacity": 20, "refill_rate": 5, "now": BASE_TIME})
        ]

    @pytest.mark.asyncio
    async def test_token_bucket_prefers_capacity_and_explicit_refill_rate(self, monkeypatch):
        freeze_time(monkeypatch, token_bucket_module)
        rule = LimitRule(
            name="tb_precedence",
            algorithm="token_bucket",
            limit=100,
            capacity=20,
            window=10,
            refill_rate=1.5,
        )
        storage = AsyncSpyStorage()

        result = await AsyncTokenBucketAlgorithm().check("client:tb-precedence", rule, storage)  # type: ignore[arg-type]

        assert storage.calls == [
            ("token_bucket", {"key": f"{rule.name}:client:tb-precedence", "capacity": 20, "refill_rate": 1.5, "now": BASE_TIME})
        ]
        assert_result(result, limit=20, rule_name="tb_precedence")

    @pytest.mark.asyncio
    async def test_leaky_bucket_derives_leak_rate_from_capacity_and_window(self, monkeypatch):
        freeze_time(monkeypatch, leaky_bucket_module)
        rule = LimitRule(name="lb_window", algorithm="leaky_bucket", capacity=20, window=4)
        storage = AsyncSpyStorage()

        await AsyncLeakyBucketAlgorithm().check("client:lb-window", rule, storage)  # type: ignore[arg-type]

        assert storage.calls == [
            ("leaky_bucket", {"key": f"{rule.name}:client:lb-window", "capacity": 20, "leak_rate": 5, "now": BASE_TIME})
        ]

    @pytest.mark.asyncio
    async def test_leaky_bucket_prefers_capacity_and_explicit_leak_rate(self, monkeypatch):
        freeze_time(monkeypatch, leaky_bucket_module)
        rule = LimitRule(
            name="lb_precedence",
            algorithm="leaky_bucket",
            limit=100,
            capacity=20,
            window=10,
            leak_rate=1.5,
        )
        storage = AsyncSpyStorage()

        result = await AsyncLeakyBucketAlgorithm().check("client:lb-precedence", rule, storage)  # type: ignore[arg-type]

        assert storage.calls == [
            ("leaky_bucket", {"key": f"{rule.name}:client:lb-precedence", "capacity": 20, "leak_rate": 1.5, "now": BASE_TIME})
        ]
        assert_result(result, limit=20, rule_name="lb_precedence")

    @pytest.mark.asyncio
    async def test_leaky_bucket_uses_limit_as_capacity_fallback(self, monkeypatch):
        freeze_time(monkeypatch, leaky_bucket_module)
        rule = LimitRule(name="lb_limit", algorithm="leaky_bucket", limit=9, leak_rate=3)
        storage = AsyncSpyStorage()

        result = await AsyncLeakyBucketAlgorithm().check("client:lb", rule, storage)  # type: ignore[arg-type]

        assert storage.calls == [
            ("leaky_bucket", {"key": f"{rule.name}:client:lb", "capacity": 9, "leak_rate": 3, "now": BASE_TIME})
        ]
        assert_result(result, limit=9, rule_name="lb_limit")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("algorithm", "rule", "message"),
        [
            (
                AsyncSlidingWindowAlgorithm(),
                LimitRule.model_construct(name="bad_sw", algorithm="sliding_window", limit=None, window=60),
                "limit",
            ),
            (
                AsyncSlidingWindowAlgorithm(),
                LimitRule.model_construct(name="bad_sw", algorithm="sliding_window", limit=10, window=None),
                "window",
            ),
            (
                AsyncFixedWindowAlgorithm(),
                LimitRule.model_construct(name="bad_fw", algorithm="fixed_window", limit=None, window=60),
                "limit",
            ),
            (
                AsyncFixedWindowAlgorithm(),
                LimitRule.model_construct(name="bad_fw", algorithm="fixed_window", limit=10, window=None),
                "window",
            ),
            (
                AsyncTokenBucketAlgorithm(),
                LimitRule.model_construct(name="bad_tb", algorithm="token_bucket", capacity=None, limit=None, refill_rate=1),
                "capacity",
            ),
            (
                AsyncTokenBucketAlgorithm(),
                LimitRule.model_construct(name="bad_tb", algorithm="token_bucket", capacity=10, refill_rate=None, window=None),
                "refill_rate",
            ),
            (
                AsyncTokenBucketAlgorithm(),
                LimitRule.model_construct(name="bad_tb", algorithm="token_bucket", capacity=10, refill_rate=0),
                "positive",
            ),
            (
                AsyncLeakyBucketAlgorithm(),
                LimitRule.model_construct(name="bad_lb", algorithm="leaky_bucket", capacity=None, limit=None, leak_rate=1),
                "capacity",
            ),
            (
                AsyncLeakyBucketAlgorithm(),
                LimitRule.model_construct(name="bad_lb", algorithm="leaky_bucket", capacity=10, leak_rate=None),
                "leak_rate",
            ),
            (
                AsyncLeakyBucketAlgorithm(),
                LimitRule.model_construct(name="bad_lb", algorithm="leaky_bucket", capacity=10, leak_rate=0),
                "positive",
            ),
            (
                AsyncGcraAlgorithm(),
                LimitRule.model_construct(name="bad_gcra", algorithm="gcra", capacity=None, limit=None, refill_rate=1),
                "capacity",
            ),
            (
                AsyncGcraAlgorithm(),
                LimitRule.model_construct(name="bad_gcra", algorithm="gcra", capacity=10, refill_rate=None),
                "refill_rate",
            ),
            (
                AsyncGcraAlgorithm(),
                LimitRule.model_construct(name="bad_gcra", algorithm="gcra", capacity=10, refill_rate=0),
                "positive",
            ),
        ],
    )
    async def test_invalid_rule_shapes_raise_clear_value_error(self, algorithm, rule, message):
        with pytest.raises(ValueError, match=message):
            await algorithm.check("client:bad", rule, AsyncSpyStorage())  # type: ignore[arg-type]


class TestSyncAlgorithms:
    @pytest.mark.parametrize(
        ("algorithm", "module", "rule", "storage_method", "expected_kwargs"),
        [
            (
                SlidingWindowAlgorithm(),
                sliding_window_sync_module,
                LimitRule(name="sw_sync", algorithm="sliding_window", limit=5, window=60),
                "sliding_window",
                {"key": "client:1", "limit": 5, "window": 60, "now": BASE_TIME},
            ),
            (
                FixedWindowAlgorithm(),
                fixed_window_sync_module,
                LimitRule(name="fw_sync", algorithm="fixed_window", limit=10, window=30),
                "fixed_window",
                {"key": "client:1", "limit": 10, "window": 30, "now": BASE_TIME},
            ),
            (
                TokenBucketAlgorithm(),
                token_bucket_sync_module,
                LimitRule(name="tb_sync", algorithm="token_bucket", capacity=7, refill_rate=2.5),
                "token_bucket",
                {"key": "client:1", "capacity": 7, "refill_rate": 2.5, "now": BASE_TIME},
            ),
            (
                LeakyBucketAlgorithm(),
                leaky_bucket_sync_module,
                LimitRule(name="lb_sync", algorithm="leaky_bucket", capacity=3, leak_rate=0.75),
                "leaky_bucket",
                {"key": "client:1", "capacity": 3, "leak_rate": 0.75, "now": BASE_TIME},
            ),
            (
                GcraAlgorithm(),
                gcra_sync_module,
                LimitRule(name="gcra_sync", algorithm="gcra", capacity=7, refill_rate=2.5),
                "gcra",
                {"key": "client:1", "capacity": 7, "rate": 2.5, "now": BASE_TIME},
            ),
        ],
    )
    def test_check_calls_expected_storage_method_and_wraps_result(
        self, monkeypatch, algorithm, module, rule, storage_method, expected_kwargs
    ):
        freeze_time(monkeypatch, module)
        storage = SyncSpyStorage(response=(True, 4, RESET_AT))

        result = algorithm.check("client:1", rule, storage)  # type: ignore[arg-type]

        assert storage.calls == [(storage_method, _prefixed_expected(expected_kwargs, rule))]
        assert_result(result, limit=expected_kwargs.get("limit", expected_kwargs.get("capacity")), rule_name=rule.name)

    @pytest.mark.parametrize(
        ("algorithm", "module", "rule", "expected_limit"),
        [
            (
                SlidingWindowAlgorithm(),
                sliding_window_sync_module,
                LimitRule(name="sw_denied_sync", algorithm="sliding_window", limit=2, window=60),
                2,
            ),
            (
                FixedWindowAlgorithm(),
                fixed_window_sync_module,
                LimitRule(name="fw_denied_sync", algorithm="fixed_window", limit=2, window=60),
                2,
            ),
            (
                TokenBucketAlgorithm(),
                token_bucket_sync_module,
                LimitRule(name="tb_denied_sync", algorithm="token_bucket", capacity=2, refill_rate=1),
                2,
            ),
            (
                LeakyBucketAlgorithm(),
                leaky_bucket_sync_module,
                LimitRule(name="lb_denied_sync", algorithm="leaky_bucket", capacity=2, leak_rate=1),
                2,
            ),
        ],
    )
    def test_denied_storage_decision_is_preserved(self, monkeypatch, algorithm, module, rule, expected_limit):
        freeze_time(monkeypatch, module)
        storage = SyncSpyStorage(response=(False, 0, RESET_AT))

        result = algorithm.check("client:denied", rule, storage)  # type: ignore[arg-type]

        assert_result(result, allowed=False, remaining=0, limit=expected_limit, rule_name=rule.name)

    def test_token_bucket_uses_limit_as_capacity_fallback(self, monkeypatch):
        freeze_time(monkeypatch, token_bucket_sync_module)
        rule = LimitRule(name="tb_limit_sync", algorithm="token_bucket", limit=12, refill_rate=3)
        storage = SyncSpyStorage()

        result = TokenBucketAlgorithm().check("client:tb", rule, storage)  # type: ignore[arg-type]

        assert storage.calls == [
            ("token_bucket", {"key": f"{rule.name}:client:tb", "capacity": 12, "refill_rate": 3, "now": BASE_TIME})
        ]
        assert_result(result, limit=12, rule_name="tb_limit_sync")

    def test_gcra_uses_limit_as_capacity_fallback_sync(self, monkeypatch):
        freeze_time(monkeypatch, gcra_sync_module)
        rule = LimitRule(name="gcra_limit_sync", algorithm="gcra", limit=12, refill_rate=3)
        storage = SyncSpyStorage()

        result = GcraAlgorithm().check("client:gcra", rule, storage)  # type: ignore[arg-type]

        assert storage.calls == [
            ("gcra", {"key": f"{rule.name}:client:gcra", "capacity": 12, "rate": 3, "now": BASE_TIME})
        ]
        assert_result(result, limit=12, rule_name="gcra_limit_sync")

    def test_token_bucket_derives_refill_rate_from_capacity_and_window(self, monkeypatch):
        freeze_time(monkeypatch, token_bucket_sync_module)
        rule = LimitRule(name="tb_window_sync", algorithm="token_bucket", capacity=20, window=4)
        storage = SyncSpyStorage()

        TokenBucketAlgorithm().check("client:tb-window", rule, storage)  # type: ignore[arg-type]

        assert storage.calls == [
            ("token_bucket", {"key": f"{rule.name}:client:tb-window", "capacity": 20, "refill_rate": 5, "now": BASE_TIME})
        ]

    def test_token_bucket_prefers_capacity_and_explicit_refill_rate(self, monkeypatch):
        freeze_time(monkeypatch, token_bucket_sync_module)
        rule = LimitRule(
            name="tb_precedence_sync",
            algorithm="token_bucket",
            limit=100,
            capacity=20,
            window=10,
            refill_rate=1.5,
        )
        storage = SyncSpyStorage()

        result = TokenBucketAlgorithm().check("client:tb-precedence", rule, storage)  # type: ignore[arg-type]

        assert storage.calls == [
            ("token_bucket", {"key": f"{rule.name}:client:tb-precedence", "capacity": 20, "refill_rate": 1.5, "now": BASE_TIME})
        ]
        assert_result(result, limit=20, rule_name="tb_precedence_sync")

    def test_leaky_bucket_derives_leak_rate_from_capacity_and_window(self, monkeypatch):
        freeze_time(monkeypatch, leaky_bucket_sync_module)
        rule = LimitRule(name="lb_window_sync", algorithm="leaky_bucket", capacity=20, window=4)
        storage = SyncSpyStorage()

        LeakyBucketAlgorithm().check("client:lb-window", rule, storage)  # type: ignore[arg-type]

        assert storage.calls == [
            ("leaky_bucket", {"key": f"{rule.name}:client:lb-window", "capacity": 20, "leak_rate": 5, "now": BASE_TIME})
        ]

    def test_leaky_bucket_prefers_capacity_and_explicit_leak_rate(self, monkeypatch):
        freeze_time(monkeypatch, leaky_bucket_sync_module)
        rule = LimitRule(
            name="lb_precedence_sync",
            algorithm="leaky_bucket",
            limit=100,
            capacity=20,
            window=10,
            leak_rate=1.5,
        )
        storage = SyncSpyStorage()

        result = LeakyBucketAlgorithm().check("client:lb-precedence", rule, storage)  # type: ignore[arg-type]

        assert storage.calls == [
            ("leaky_bucket", {"key": f"{rule.name}:client:lb-precedence", "capacity": 20, "leak_rate": 1.5, "now": BASE_TIME})
        ]
        assert_result(result, limit=20, rule_name="lb_precedence_sync")

    def test_leaky_bucket_uses_limit_as_capacity_fallback(self, monkeypatch):
        freeze_time(monkeypatch, leaky_bucket_sync_module)
        rule = LimitRule(name="lb_limit_sync", algorithm="leaky_bucket", limit=9, leak_rate=3)
        storage = SyncSpyStorage()

        result = LeakyBucketAlgorithm().check("client:lb", rule, storage)  # type: ignore[arg-type]

        assert storage.calls == [
            ("leaky_bucket", {"key": f"{rule.name}:client:lb", "capacity": 9, "leak_rate": 3, "now": BASE_TIME})
        ]
        assert_result(result, limit=9, rule_name="lb_limit_sync")

    def test_leaky_bucket_prefers_capacity_over_limit(self, monkeypatch):
        freeze_time(monkeypatch, leaky_bucket_sync_module)
        rule = LimitRule(name="lb_precedence_sync", algorithm="leaky_bucket", limit=100, capacity=8, leak_rate=2)
        storage = SyncSpyStorage()

        result = LeakyBucketAlgorithm().check("client:lb-precedence", rule, storage)  # type: ignore[arg-type]

        assert storage.calls == [
            ("leaky_bucket", {"key": f"{rule.name}:client:lb-precedence", "capacity": 8, "leak_rate": 2, "now": BASE_TIME})
        ]
        assert_result(result, limit=8, rule_name="lb_precedence_sync")

    @pytest.mark.parametrize(
        ("algorithm", "rule", "message"),
        [
            (
                SlidingWindowAlgorithm(),
                LimitRule.model_construct(name="bad_sw", algorithm="sliding_window", limit=None, window=60),
                "limit",
            ),
            (
                SlidingWindowAlgorithm(),
                LimitRule.model_construct(name="bad_sw", algorithm="sliding_window", limit=10, window=None),
                "window",
            ),
            (
                FixedWindowAlgorithm(),
                LimitRule.model_construct(name="bad_fw", algorithm="fixed_window", limit=None, window=60),
                "limit",
            ),
            (
                FixedWindowAlgorithm(),
                LimitRule.model_construct(name="bad_fw", algorithm="fixed_window", limit=10, window=None),
                "window",
            ),
            (
                TokenBucketAlgorithm(),
                LimitRule.model_construct(name="bad_tb", algorithm="token_bucket", capacity=None, limit=None, refill_rate=1),
                "capacity",
            ),
            (
                TokenBucketAlgorithm(),
                LimitRule.model_construct(name="bad_tb", algorithm="token_bucket", capacity=10, refill_rate=None, window=None),
                "refill_rate",
            ),
            (
                TokenBucketAlgorithm(),
                LimitRule.model_construct(name="bad_tb", algorithm="token_bucket", capacity=10, refill_rate=0),
                "positive",
            ),
            (
                LeakyBucketAlgorithm(),
                LimitRule.model_construct(name="bad_lb", algorithm="leaky_bucket", capacity=None, limit=None, leak_rate=1),
                "capacity",
            ),
            (
                LeakyBucketAlgorithm(),
                LimitRule.model_construct(name="bad_lb", algorithm="leaky_bucket", capacity=10, leak_rate=None),
                "leak_rate",
            ),
            (
                LeakyBucketAlgorithm(),
                LimitRule.model_construct(name="bad_lb", algorithm="leaky_bucket", capacity=10, leak_rate=0),
                "positive",
            ),
            (
                GcraAlgorithm(),
                LimitRule.model_construct(name="bad_gcra", algorithm="gcra", capacity=None, limit=None, refill_rate=1),
                "capacity",
            ),
            (
                GcraAlgorithm(),
                LimitRule.model_construct(name="bad_gcra", algorithm="gcra", capacity=10, refill_rate=None),
                "refill_rate",
            ),
            (
                GcraAlgorithm(),
                LimitRule.model_construct(name="bad_gcra", algorithm="gcra", capacity=10, refill_rate=0),
                "positive",
            ),
        ],
    )
    def test_invalid_rule_shapes_raise_clear_value_error(self, algorithm, rule, message):
        with pytest.raises(ValueError, match=message):
            algorithm.check("client:bad", rule, SyncSpyStorage())  # type: ignore[arg-type]
