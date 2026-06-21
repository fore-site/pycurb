import pytest
import math

ASYNC_STORAGE_FIXTURES = [
    "async_memory_storage",
    "async_redis_storage",
    "async_redis_storage_sentinel",
    "async_redis_storage_cluster",
    "async_redis_storage_tls",
]
SYNC_STORAGE_FIXTURES = [
    "sync_memory_storage",
    "sync_redis_storage",
    "sync_redis_storage_sentinel",
    "sync_redis_storage_cluster",
    "sync_redis_storage_tls",
]
BASE_TIME = 1_700_000_000.25
EPSILON = 0.001


class TestSlidingWindow:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_within_limit(self, storage_fixture):
        storage = storage_fixture
        key = "sw1"
        window = 10
        limit = 3
        now = BASE_TIME
        # 3 allowed requests
        for i in range(limit):
            allowed, remaining, reset_at = await storage.sliding_window(
                key, window, limit, now + i * 0.1
            )
            assert allowed is True
            assert remaining == limit - (i + 1)
            assert reset_at >= now + window
        # 4th request denied
        allowed, remaining, reset_at = await storage.sliding_window(
            key, window, limit, now + 0.4
        )
        assert allowed is False
        assert remaining == 0
        assert reset_at > now + 0.4

    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_expiration(self, storage_fixture):
        storage = storage_fixture
        key = "sw_expire"
        window = 2
        limit = 1
        now = BASE_TIME
        # First request allowed
        allowed, _, _ = await storage.sliding_window(key, window, limit, now)
        assert allowed is True
        # Second request just before window ends (1.9s later) -> denied
        allowed, _, _ = await storage.sliding_window(key, window, limit, now + 1.9)
        assert allowed is False
        # Third request after window (2.1s later) -> allowed
        allowed, _, _ = await storage.sliding_window(key, window, limit, now + 2.1)
        assert allowed is True

    # Sync versions
    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_within_limit_sync(self, storage_fixture):
        storage = storage_fixture
        key = "sw_sync1"
        window = 10
        limit = 3
        now = BASE_TIME
        for i in range(limit):
            allowed, remaining, _ = storage.sliding_window(
                key, window, limit, now + i * 0.1
            )
            assert allowed is True
            assert remaining == limit - (i + 1)
        allowed, remaining, _ = storage.sliding_window(key, window, limit, now + 0.4)
        assert allowed is False

    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_expiration_sync(self, storage_fixture):
        storage = storage_fixture
        key = "sw_expire_sync"
        window = 2
        limit = 1
        now = BASE_TIME
        allowed, _, _ = storage.sliding_window(key, window, limit, now)
        assert allowed is True
        allowed, _, _ = storage.sliding_window(key, window, limit, now + 1.9)
        assert allowed is False
        allowed, _, _ = storage.sliding_window(key, window, limit, now + 2.1)
        assert allowed is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_exact_reset_boundary_allows(self, storage_fixture):
        storage = storage_fixture
        key = "sw_boundary"
        window = 2
        limit = 1
        now = BASE_TIME

        allowed, remaining, reset_at = await storage.sliding_window(
            key, window, limit, now
        )
        assert allowed is True
        assert remaining == 0
        assert reset_at == pytest.approx(now + window)

        allowed, remaining, reset_at = await storage.sliding_window(
            key, window, limit, now + window
        )
        assert allowed is True
        assert remaining == 0
        assert reset_at == pytest.approx(now + window * 2)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_keys_are_isolated(self, storage_fixture):
        storage = storage_fixture
        window = 10
        limit = 1
        now = BASE_TIME

        assert (await storage.sliding_window("sw_a", window, limit, now))[0] is True
        assert (await storage.sliding_window("sw_a", window, limit, now + 0.1))[
            0
        ] is False

        allowed, remaining, _ = await storage.sliding_window(
            "sw_b", window, limit, now + 0.1
        )
        assert allowed is True
        assert remaining == 0

    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_exact_reset_boundary_allows_sync(self, storage_fixture):
        storage = storage_fixture
        key = "sw_boundary_sync"
        window = 2
        limit = 1
        now = BASE_TIME

        allowed, remaining, reset_at = storage.sliding_window(key, window, limit, now)
        assert allowed is True
        assert remaining == 0
        assert reset_at == pytest.approx(now + window)

        allowed, remaining, reset_at = storage.sliding_window(
            key, window, limit, now + window
        )
        assert allowed is True
        assert remaining == 0
        assert reset_at == pytest.approx(now + window * 2)

    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_keys_are_isolated_sync(self, storage_fixture):
        storage = storage_fixture
        window = 10
        limit = 1
        now = BASE_TIME

        assert storage.sliding_window("sw_sync_a", window, limit, now)[0] is True
        assert storage.sliding_window("sw_sync_a", window, limit, now + 0.1)[0] is False

        allowed, remaining, _ = storage.sliding_window(
            "sw_sync_b", window, limit, now + 0.1
        )
        assert allowed is True
        assert remaining == 0


class TestFixedWindow:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_within_limit(self, storage_fixture):
        storage = storage_fixture
        key = "fw1"
        window = 10
        limit = 3
        now = BASE_TIME
        for i in range(limit):
            allowed, remaining, reset_at = await storage.fixed_window(
                key, window, limit, now + i * 0.1
            )
            assert allowed is True
            assert remaining == limit - (i + 1)
            expected_reset = math.floor((now + i * 0.1) / window) * window + window
            assert abs(reset_at - expected_reset) < 0.1
        # 4th request denied
        allowed, remaining, reset_at = await storage.fixed_window(
            key, window, limit, now + 0.5
        )
        assert allowed is False
        assert remaining == 0
        assert reset_at > now

    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_window_reset(self, storage_fixture):
        storage = storage_fixture
        key = "fw_reset"
        window = 2
        limit = 2
        now = BASE_TIME
        # Fill window
        await storage.fixed_window(key, window, limit, now)
        await storage.fixed_window(key, window, limit, now + 0.1)
        # Next request in same window denies
        allowed, _, _ = await storage.fixed_window(key, window, limit, now + 0.2)
        assert allowed is False
        # After window passes (now+2.1), new window allows
        allowed, _, _ = await storage.fixed_window(key, window, limit, now + 2.1)
        assert allowed is True

    # Sync versions
    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_within_limit_sync(self, storage_fixture):
        storage = storage_fixture
        key = "fw_sync1"
        window = 10
        limit = 3
        now = BASE_TIME
        for i in range(limit):
            allowed, _, _ = storage.fixed_window(key, window, limit, now + i * 0.1)
            assert allowed is True
        allowed, _, _ = storage.fixed_window(key, window, limit, now + 0.5)
        assert allowed is False

    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_window_reset_sync(self, storage_fixture):
        storage = storage_fixture
        key = "fw_reset_sync"
        window = 2
        limit = 2
        now = BASE_TIME
        storage.fixed_window(key, window, limit, now)
        storage.fixed_window(key, window, limit, now + 0.1)
        allowed, _, _ = storage.fixed_window(key, window, limit, now + 0.2)
        assert allowed is False
        allowed, _, _ = storage.fixed_window(key, window, limit, now + 2.1)
        assert allowed is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_exact_aligned_window_boundary_allows(self, storage_fixture):
        storage = storage_fixture
        key = "fw_boundary"
        window = 10
        limit = 1
        now = BASE_TIME
        window_start = math.floor(now / window) * window
        reset_at = window_start + window

        allowed, remaining, observed_reset = await storage.fixed_window(
            key, window, limit, now
        )
        assert allowed is True
        assert remaining == 0
        assert observed_reset == pytest.approx(reset_at)

        allowed, remaining, observed_reset = await storage.fixed_window(
            key, window, limit, reset_at - EPSILON
        )
        assert allowed is False
        assert remaining == 0
        assert observed_reset == pytest.approx(reset_at)

        allowed, remaining, observed_reset = await storage.fixed_window(
            key, window, limit, reset_at
        )
        assert allowed is True
        assert remaining == 0
        assert observed_reset == pytest.approx(reset_at + window)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_keys_are_isolated(self, storage_fixture):
        storage = storage_fixture
        window = 10
        limit = 1
        now = BASE_TIME

        assert (await storage.fixed_window("fw_a", window, limit, now))[0] is True
        assert (await storage.fixed_window("fw_a", window, limit, now + 0.1))[
            0
        ] is False

        allowed, remaining, _ = await storage.fixed_window(
            "fw_b", window, limit, now + 0.1
        )
        assert allowed is True
        assert remaining == 0

    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_exact_aligned_window_boundary_allows_sync(self, storage_fixture):
        storage = storage_fixture
        key = "fw_boundary_sync"
        window = 10
        limit = 1
        now = BASE_TIME
        window_start = math.floor(now / window) * window
        reset_at = window_start + window

        allowed, remaining, observed_reset = storage.fixed_window(
            key, window, limit, now
        )
        assert allowed is True
        assert remaining == 0
        assert observed_reset == pytest.approx(reset_at)

        allowed, remaining, observed_reset = storage.fixed_window(
            key, window, limit, reset_at - EPSILON
        )
        assert allowed is False
        assert remaining == 0
        assert observed_reset == pytest.approx(reset_at)

        allowed, remaining, observed_reset = storage.fixed_window(
            key, window, limit, reset_at
        )
        assert allowed is True
        assert remaining == 0
        assert observed_reset == pytest.approx(reset_at + window)

    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_keys_are_isolated_sync(self, storage_fixture):
        storage = storage_fixture
        window = 10
        limit = 1
        now = BASE_TIME

        assert storage.fixed_window("fw_sync_a", window, limit, now)[0] is True
        assert storage.fixed_window("fw_sync_a", window, limit, now + 0.1)[0] is False

        allowed, remaining, _ = storage.fixed_window(
            "fw_sync_b", window, limit, now + 0.1
        )
        assert allowed is True
        assert remaining == 0


class TestTokenBucket:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_initial_full(self, storage_fixture):
        storage = storage_fixture
        key = "tb1"
        capacity = 10
        refill_rate = 1.0
        now = BASE_TIME
        allowed, remaining, reset_at = await storage.token_bucket(
            key, capacity, refill_rate, now
        )
        assert allowed is True
        assert remaining == capacity - 1
        # reset_at should be time when bucket becomes full: now + (capacity - remaining)/rate
        expected_reset = now + (capacity - remaining) / refill_rate
        assert abs(reset_at - expected_reset) < 0.1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_exhaust_and_refill(self, storage_fixture):
        storage = storage_fixture
        key = "tb_exhaust"
        capacity = 2
        refill_rate = 1.0
        now = BASE_TIME
        # Consume both tokens
        for i in range(capacity):
            allowed, _, _ = await storage.token_bucket(
                key, capacity, refill_rate, now + i * 0.1
            )
            assert allowed is True
        # Next request denied
        allowed, _, _ = await storage.token_bucket(
            key, capacity, refill_rate, now + 0.3
        )
        assert allowed is False
        # Advance by enough simulated time for one token to refill.
        new_now = now + 1.1
        allowed, remaining, _ = await storage.token_bucket(
            key, capacity, refill_rate, new_now
        )
        assert allowed is True
        assert remaining == 0  # after consuming one token, bucket empty again

    # Sync versions
    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_initial_full_sync(self, storage_fixture):
        storage = storage_fixture
        key = "tb_sync1"
        capacity = 10
        refill_rate = 1.0
        now = BASE_TIME
        allowed, remaining, _ = storage.token_bucket(key, capacity, refill_rate, now)
        assert allowed is True
        assert remaining == capacity - 1

    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_exhaust_and_refill_sync(self, storage_fixture):
        storage = storage_fixture
        key = "tb_exhaust_sync"
        capacity = 2
        refill_rate = 1.0
        now = BASE_TIME
        for i in range(capacity):
            allowed, _, _ = storage.token_bucket(
                key, capacity, refill_rate, now + i * 0.1
            )
            assert allowed is True
        allowed, _, _ = storage.token_bucket(key, capacity, refill_rate, now + 0.3)
        assert allowed is False
        new_now = now + 1.1
        allowed, _, _ = storage.token_bucket(key, capacity, refill_rate, new_now)
        assert allowed is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_partial_refill_denies_until_one_token_available(
        self, storage_fixture
    ):
        storage = storage_fixture
        key = "tb_partial"
        capacity = 1
        refill_rate = 1.0
        now = BASE_TIME

        assert (await storage.token_bucket(key, capacity, refill_rate, now))[0] is True

        allowed, remaining, reset_at = await storage.token_bucket(
            key, capacity, refill_rate, now + 0.999
        )
        assert allowed is False
        assert remaining == 0
        assert reset_at == pytest.approx(now + 1.0)

        allowed, remaining, reset_at = await storage.token_bucket(
            key, capacity, refill_rate, now + 1.0
        )
        assert allowed is True
        assert remaining == 0
        assert reset_at == pytest.approx(now + 2.0)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_refill_caps_at_capacity_after_idle(self, storage_fixture):
        storage = storage_fixture
        key = "tb_cap"
        capacity = 3
        refill_rate = 1.0
        now = BASE_TIME

        assert (await storage.token_bucket(key, capacity, refill_rate, now))[1] == 2

        idle_now = now + 100
        allowed, remaining, reset_at = await storage.token_bucket(
            key, capacity, refill_rate, idle_now
        )
        assert allowed is True
        assert remaining == capacity - 1
        assert reset_at == pytest.approx(idle_now + 1)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_keys_are_isolated(self, storage_fixture):
        storage = storage_fixture
        capacity = 1
        refill_rate = 0.5
        now = BASE_TIME

        assert (await storage.token_bucket("tb_a", capacity, refill_rate, now))[
            0
        ] is True
        assert (await storage.token_bucket("tb_a", capacity, refill_rate, now + 0.1))[
            0
        ] is False

        allowed, remaining, _ = await storage.token_bucket(
            "tb_b", capacity, refill_rate, now + 0.1
        )
        assert allowed is True
        assert remaining == 0

    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_partial_refill_denies_until_one_token_available_sync(
        self, storage_fixture
    ):
        storage = storage_fixture
        key = "tb_partial_sync"
        capacity = 1
        refill_rate = 1.0
        now = BASE_TIME

        assert storage.token_bucket(key, capacity, refill_rate, now)[0] is True

        allowed, remaining, reset_at = storage.token_bucket(
            key, capacity, refill_rate, now + 0.999
        )
        assert allowed is False
        assert remaining == 0
        assert reset_at == pytest.approx(now + 1.0)

        allowed, remaining, reset_at = storage.token_bucket(
            key, capacity, refill_rate, now + 1.0
        )
        assert allowed is True
        assert remaining == 0
        assert reset_at == pytest.approx(now + 2.0)

    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_refill_caps_at_capacity_after_idle_sync(self, storage_fixture):
        storage = storage_fixture
        key = "tb_cap_sync"
        capacity = 3
        refill_rate = 1.0
        now = BASE_TIME

        assert storage.token_bucket(key, capacity, refill_rate, now)[1] == 2

        idle_now = now + 100
        allowed, remaining, reset_at = storage.token_bucket(
            key, capacity, refill_rate, idle_now
        )
        assert allowed is True
        assert remaining == capacity - 1
        assert reset_at == pytest.approx(idle_now + 1)

    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_keys_are_isolated_sync(self, storage_fixture):
        storage = storage_fixture
        capacity = 1
        refill_rate = 0.5
        now = BASE_TIME

        assert storage.token_bucket("tb_sync_a", capacity, refill_rate, now)[0] is True
        assert (
            storage.token_bucket("tb_sync_a", capacity, refill_rate, now + 0.1)[0]
            is False
        )

        allowed, remaining, _ = storage.token_bucket(
            "tb_sync_b", capacity, refill_rate, now + 0.1
        )
        assert allowed is True
        assert remaining == 0


class TestLeakyBucket:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_initial_empty(self, storage_fixture):
        storage = storage_fixture
        key = "lb1"
        capacity = 5
        leak_rate = 1.0
        now = BASE_TIME
        allowed, remaining, reset_at = await storage.leaky_bucket(
            key, capacity, leak_rate, now
        )
        assert allowed is True
        assert remaining == capacity - 1
        # reset_at should be now + 1/leak_rate (time of next leak)
        assert abs(reset_at - (now + 1.0)) < 0.1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_fill_and_leak(self, storage_fixture):
        storage = storage_fixture
        key = "lb_fill"
        capacity = 2
        leak_rate = 1.0
        now = BASE_TIME
        # Fill bucket
        for i in range(capacity):
            allowed, _, _ = await storage.leaky_bucket(
                key, capacity, leak_rate, now + i * 0.1
            )
            assert allowed is True
        # Next request denied
        allowed, _, _ = await storage.leaky_bucket(key, capacity, leak_rate, now + 0.2)
        assert allowed is False
        # Advance by enough simulated time for one queued request to leak.
        new_now = now + 1.1
        allowed, remaining, _ = await storage.leaky_bucket(
            key, capacity, leak_rate, new_now
        )
        assert allowed is True
        assert remaining == 0

    # Sync versions
    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_initial_empty_sync(self, storage_fixture):
        storage = storage_fixture
        key = "lb_sync1"
        capacity = 5
        leak_rate = 1.0
        now = BASE_TIME
        allowed, remaining, _ = storage.leaky_bucket(key, capacity, leak_rate, now)
        assert allowed is True
        assert remaining == capacity - 1

    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_fill_and_leak_sync(self, storage_fixture):
        storage = storage_fixture
        key = "lb_fill_sync"
        capacity = 2
        leak_rate = 1.0
        now = BASE_TIME
        for i in range(capacity):
            allowed, _, _ = storage.leaky_bucket(
                key, capacity, leak_rate, now + i * 0.1
            )
            assert allowed is True
        allowed, _, _ = storage.leaky_bucket(key, capacity, leak_rate, now + 0.2)
        assert allowed is False
        new_now = now + 1.1
        allowed, _, _ = storage.leaky_bucket(key, capacity, leak_rate, new_now)
        assert allowed is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_fractional_leak_waits_for_full_interval(self, storage_fixture):
        storage = storage_fixture
        key = "lb_fractional"
        capacity = 2
        leak_rate = 1.0
        now = BASE_TIME

        assert (await storage.leaky_bucket(key, capacity, leak_rate, now))[0] is True
        assert (await storage.leaky_bucket(key, capacity, leak_rate, now + 0.1))[
            0
        ] is True

        allowed, remaining, reset_at = await storage.leaky_bucket(
            key, capacity, leak_rate, now + 0.999
        )
        assert allowed is False
        assert remaining == 0
        assert reset_at == pytest.approx(now + 1.999)

        allowed, remaining, _ = await storage.leaky_bucket(
            key, capacity, leak_rate, now + 1.0
        )
        assert allowed is True
        assert remaining == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_multiple_leaks_after_idle(self, storage_fixture):
        storage = storage_fixture
        key = "lb_idle"
        capacity = 3
        leak_rate = 1.0
        now = BASE_TIME

        for offset in (0, 0.1, 0.2):
            allowed, _, _ = await storage.leaky_bucket(
                key, capacity, leak_rate, now + offset
            )
            assert allowed is True

        allowed, remaining, reset_at = await storage.leaky_bucket(
            key, capacity, leak_rate, now + 3.2
        )
        assert allowed is True
        assert remaining == capacity - 1
        assert reset_at == pytest.approx(now + 4.2)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_keys_are_isolated(self, storage_fixture):
        storage = storage_fixture
        capacity = 1
        leak_rate = 1.0
        now = BASE_TIME

        assert (await storage.leaky_bucket("lb_a", capacity, leak_rate, now))[0] is True
        assert (await storage.leaky_bucket("lb_a", capacity, leak_rate, now + 0.1))[
            0
        ] is False

        allowed, remaining, _ = await storage.leaky_bucket(
            "lb_b", capacity, leak_rate, now + 0.1
        )
        assert allowed is True
        assert remaining == 0

    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_fractional_leak_waits_for_full_interval_sync(self, storage_fixture):
        storage = storage_fixture
        key = "lb_fractional_sync"
        capacity = 2
        leak_rate = 1.0
        now = BASE_TIME

        assert storage.leaky_bucket(key, capacity, leak_rate, now)[0] is True
        assert storage.leaky_bucket(key, capacity, leak_rate, now + 0.1)[0] is True

        allowed, remaining, reset_at = storage.leaky_bucket(
            key, capacity, leak_rate, now + 0.999
        )
        assert allowed is False
        assert remaining == 0
        assert reset_at == pytest.approx(now + 1.999)

        allowed, remaining, _ = storage.leaky_bucket(
            key, capacity, leak_rate, now + 1.0
        )
        assert allowed is True
        assert remaining == 0

    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_multiple_leaks_after_idle_sync(self, storage_fixture):
        storage = storage_fixture
        key = "lb_idle_sync"
        capacity = 3
        leak_rate = 1.0
        now = BASE_TIME

        for offset in (0, 0.1, 0.2):
            allowed, _, _ = storage.leaky_bucket(key, capacity, leak_rate, now + offset)
            assert allowed is True

        allowed, remaining, reset_at = storage.leaky_bucket(
            key, capacity, leak_rate, now + 3.2
        )
        assert allowed is True
        assert remaining == capacity - 1
        assert reset_at == pytest.approx(now + 4.2)

    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_keys_are_isolated_sync(self, storage_fixture):
        storage = storage_fixture
        capacity = 1
        leak_rate = 1.0
        now = BASE_TIME

        assert storage.leaky_bucket("lb_sync_a", capacity, leak_rate, now)[0] is True
        assert (
            storage.leaky_bucket("lb_sync_a", capacity, leak_rate, now + 0.1)[0]
            is False
        )

        allowed, remaining, _ = storage.leaky_bucket(
            "lb_sync_b", capacity, leak_rate, now + 0.1
        )
        assert allowed is True
        assert remaining == 0


class TestRedisStorageServerTimeAsync:
    @pytest.mark.asyncio
    async def test_sliding_window_with_server_time(
        self, async_redis_storage_with_server_time
    ):
        storage = async_redis_storage_with_server_time
        key = "sw_server"
        window = 10
        limit = 3
        # Execute 3 allowed requests
        for i in range(limit):
            allowed, remaining, reset_at = await storage.sliding_window(
                key, window, limit, now=0
            )  # now ignored
            assert allowed is True
            assert remaining == limit - i - 1
        # Fourth request should be denied
        allowed, remaining, reset_at = await storage.sliding_window(
            key, window, limit, now=0
        )
        assert allowed is False
        assert remaining == 0
        # reset_at should be > current mocked time (which advanced)
        assert reset_at > 1000.0

    @pytest.mark.asyncio
    async def test_fixed_window_with_server_time(
        self, async_redis_storage_with_server_time
    ):
        storage = async_redis_storage_with_server_time
        key = "fw_server"
        window = 10
        limit = 2
        # First request allowed
        allowed, remaining, _ = await storage.fixed_window(key, window, limit, now=0)
        assert allowed is True
        assert remaining == 1
        # Second allowed
        allowed, remaining, _ = await storage.fixed_window(key, window, limit, now=0)
        assert allowed is True
        assert remaining == 0
        # Third denied
        allowed, remaining, _ = await storage.fixed_window(key, window, limit, now=0)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_token_bucket_with_server_time(
        self, async_redis_storage_with_server_time
    ):
        storage = async_redis_storage_with_server_time
        key = "tb_server"
        capacity = 3
        refill_rate = 1.0
        # Consume all tokens
        for i in range(capacity):
            allowed, remaining, _ = await storage.token_bucket(
                key, capacity, refill_rate, now=0
            )
            assert allowed is True
            assert remaining == capacity - i - 1
        # Next denied
        allowed, remaining, _ = await storage.token_bucket(
            key, capacity, refill_rate, now=0
        )
        assert allowed is False
        pass

    @pytest.mark.asyncio
    async def test_leaky_bucket_with_server_time(
        self, async_redis_storage_with_server_time
    ):
        storage = async_redis_storage_with_server_time
        key = "lb_server"
        capacity = 2
        leak_rate = 1.0
        # Fill bucket
        for i in range(capacity):
            allowed, remaining, _ = await storage.leaky_bucket(
                key, capacity, leak_rate, now=0
            )
            assert allowed is True
            assert remaining == capacity - i - 1
        # Third denied
        allowed, remaining, _ = await storage.leaky_bucket(
            key, capacity, leak_rate, now=0
        )
        assert allowed is False


# sync version
class TestRedisStorageServerTimeSync:
    def test_sliding_window_sync(self, sync_redis_storage_with_server_time):
        storage = sync_redis_storage_with_server_time
        key = "sw_sync_server"
        window = 10
        limit = 2
        for i in range(limit):
            allowed, remaining, _ = storage.sliding_window(key, window, limit, now=0)
            assert allowed is True
            assert remaining == limit - i - 1
        allowed, remaining, _ = storage.sliding_window(key, window, limit, now=0)
        assert allowed is False

    def test_fixed_window_sync(self, sync_redis_storage_with_server_time):
        storage = sync_redis_storage_with_server_time
        key = "fw_sync_server"
        window = 10
        limit = 1
        allowed, _, _ = storage.fixed_window(key, window, limit, now=0)
        assert allowed is True
        allowed, _, _ = storage.fixed_window(key, window, limit, now=0)
        assert allowed is False


class TestGcra:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_initial_full(self, storage_fixture):
        storage = storage_fixture
        key = "gcra1"
        capacity = 10
        rate = 1.0
        now = BASE_TIME
        allowed, remaining, reset_at = await storage.gcra(key, capacity, rate, now)
        assert allowed is True
        assert remaining == capacity - 1
        expected_reset = now + (capacity - remaining) / rate
        assert abs(reset_at - expected_reset) < 0.1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_exhaust_and_refill(self, storage_fixture):
        storage = storage_fixture
        key = "gcra_exhaust"
        capacity = 2
        rate = 1.0
        now = BASE_TIME
        for i in range(capacity):
            allowed, _, _ = await storage.gcra(key, capacity, rate, now + i * 0.1)
            assert allowed is True
        allowed, _, _ = await storage.gcra(key, capacity, rate, now + 0.3)
        assert allowed is False
        new_now = now + 1.1
        allowed, remaining, _ = await storage.gcra(key, capacity, rate, new_now)
        assert allowed is True
        assert remaining == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_partial_refill_denies_until_one_available(self, storage_fixture):
        storage = storage_fixture
        key = "gcra_partial"
        capacity = 1
        rate = 1.0
        now = BASE_TIME

        assert (await storage.gcra(key, capacity, rate, now))[0] is True

        allowed, remaining, reset_at = await storage.gcra(
            key, capacity, rate, now + 0.999
        )
        assert allowed is False
        assert remaining == 0
        assert reset_at == pytest.approx(now + 1.0)

        allowed, remaining, reset_at = await storage.gcra(
            key, capacity, rate, now + 1.0
        )
        assert allowed is True
        assert remaining == 0
        assert reset_at == pytest.approx(now + 2.0)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_refill_caps_at_capacity_after_idle(self, storage_fixture):
        storage = storage_fixture
        key = "gcra_cap"
        capacity = 3
        rate = 1.0
        now = BASE_TIME

        assert (await storage.gcra(key, capacity, rate, now))[1] == capacity - 1

        idle_now = now + 100
        allowed, remaining, reset_at = await storage.gcra(key, capacity, rate, idle_now)
        assert allowed is True
        assert remaining == capacity - 1
        assert reset_at == pytest.approx(idle_now + 1)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("storage_fixture", ASYNC_STORAGE_FIXTURES, indirect=True)
    async def test_keys_are_isolated(self, storage_fixture):
        storage = storage_fixture
        capacity = 1
        rate = 0.5
        now = BASE_TIME

        assert (await storage.gcra("gcra_a", capacity, rate, now))[0] is True
        assert (await storage.gcra("gcra_a", capacity, rate, now + 0.1))[0] is False

        allowed, remaining, _ = await storage.gcra("gcra_b", capacity, rate, now + 0.1)
        assert allowed is True
        assert remaining == 0

    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_partial_refill_denies_until_one_available_sync(self, storage_fixture):
        storage = storage_fixture
        key = "gcra_partial_sync"
        capacity = 1
        rate = 1.0
        now = BASE_TIME

        assert storage.gcra(key, capacity, rate, now)[0] is True

        allowed, remaining, reset_at = storage.gcra(key, capacity, rate, now + 0.999)
        assert allowed is False
        assert remaining == 0
        assert reset_at == pytest.approx(now + 1.0)

        allowed, remaining, reset_at = storage.gcra(key, capacity, rate, now + 1.0)
        assert allowed is True
        assert remaining == 0
        assert reset_at == pytest.approx(now + 2.0)

    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_refill_caps_at_capacity_after_idle_sync(self, storage_fixture):
        storage = storage_fixture
        key = "gcra_cap_sync"
        capacity = 3
        rate = 1.0
        now = BASE_TIME

        assert storage.gcra(key, capacity, rate, now)[1] == capacity - 1

        idle_now = now + 100
        allowed, remaining, reset_at = storage.gcra(key, capacity, rate, idle_now)
        assert allowed is True
        assert remaining == capacity - 1
        assert reset_at == pytest.approx(idle_now + 1)

    @pytest.mark.parametrize("storage_fixture", SYNC_STORAGE_FIXTURES, indirect=True)
    def test_keys_are_isolated_sync(self, storage_fixture):
        storage = storage_fixture
        capacity = 1
        rate = 0.5
        now = BASE_TIME

        assert storage.gcra("gcra_sync_a", capacity, rate, now)[0] is True
        assert storage.gcra("gcra_sync_a", capacity, rate, now + 0.1)[0] is False

        allowed, remaining, _ = storage.gcra("gcra_sync_b", capacity, rate, now + 0.1)
        assert allowed is True
        assert remaining == 0
