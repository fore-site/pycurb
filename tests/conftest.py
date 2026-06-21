import pytest
import pytest_asyncio
import os
import redis
import redis.asyncio as aioredis
from unittest.mock import AsyncMock, MagicMock
from pycurb.core.storage import (
    RedisStorage,
    AsyncRedisStorage,
    MemoryStorage,
    AsyncMemoryStorage,
)


def is_redis_available(host="localhost", port=6379):
    try:
        r = redis.Redis(host=host, port=port)
        return r.ping()
    except:
        return False


async def clear_async_redis_test_keys(redis_client):
    keys = [key async for key in redis_client.scan_iter(match="test:*")]
    if keys:
        await redis_client.delete(*keys)


def clear_sync_redis_test_keys(redis_client):
    keys = list(redis_client.scan_iter(match="test:*"))
    if keys:
        redis_client.delete(*keys)


# Async fixtures


@pytest_asyncio.fixture
async def async_memory_storage():
    storage = AsyncMemoryStorage()
    yield storage
    await storage.close()


@pytest_asyncio.fixture
async def async_redis_storage():
    if not is_redis_available():
        pytest.skip("Redis not available, skipping redis tests.")
    redis_client = aioredis.from_url("redis://localhost:6379", decode_responses=True)
    await clear_async_redis_test_keys(redis_client)
    storage = AsyncRedisStorage(redis_client, key_prefix="test:")
    yield storage
    await clear_async_redis_test_keys(redis_client)
    await storage.close()


@pytest_asyncio.fixture
async def async_redis_storage_sentinel():
    url = os.environ.get('REDIS_SENTINEL_URL')
    if not url:
        pytest.skip('REDIS_SENTINEL_URL not set, skipping sentinel tests.')
    redis_client = aioredis.from_url(url, decode_responses=True)
    await clear_async_redis_test_keys(redis_client)
    storage = AsyncRedisStorage(redis_client, key_prefix='test:')
    yield storage
    await clear_async_redis_test_keys(redis_client)
    await storage.close()


@pytest_asyncio.fixture
async def async_redis_storage_cluster():
    url = os.environ.get('REDIS_CLUSTER_URL')
    if not url:
        pytest.skip('REDIS_CLUSTER_URL not set, skipping cluster tests.')
    redis_client = aioredis.from_url(url, decode_responses=True)
    await clear_async_redis_test_keys(redis_client)
    storage = AsyncRedisStorage(redis_client, key_prefix='test:')
    yield storage
    await clear_async_redis_test_keys(redis_client)
    await storage.close()


@pytest_asyncio.fixture
async def async_redis_storage_tls():
    url = os.environ.get('REDIS_TLS_URL')
    if not url:
        pytest.skip('REDIS_TLS_URL not set, skipping TLS tests.')
    redis_client = aioredis.from_url(url, decode_responses=True)
    await clear_async_redis_test_keys(redis_client)
    storage = AsyncRedisStorage(redis_client, key_prefix='test:')
    yield storage
    await clear_async_redis_test_keys(redis_client)
    await storage.close()


# Sync fixtures


@pytest.fixture
def sync_memory_storage():
    storage = MemoryStorage()
    yield storage
    storage.close()


@pytest.fixture
def sync_redis_storage():
    if not is_redis_available():
        pytest.skip("Redis not available, skipping redis tests.")
    redis_client = redis.from_url("redis://localhost:6379", decode_responses=True)
    clear_sync_redis_test_keys(redis_client)
    storage = RedisStorage(redis_client, key_prefix="test:")
    yield storage
    clear_sync_redis_test_keys(redis_client)
    storage.close()


@pytest.fixture
def sync_redis_storage_sentinel():
    url = os.environ.get('REDIS_SENTINEL_URL')
    if not url:
        pytest.skip('REDIS_SENTINEL_URL not set, skipping sentinel tests.')
    redis_client = redis.from_url(url, decode_responses=True)
    clear_sync_redis_test_keys(redis_client)
    storage = RedisStorage(redis_client, key_prefix='test:')
    yield storage
    clear_sync_redis_test_keys(redis_client)
    storage.close()


@pytest.fixture
def sync_redis_storage_cluster():
    url = os.environ.get('REDIS_CLUSTER_URL')
    if not url:
        pytest.skip('REDIS_CLUSTER_URL not set, skipping cluster tests.')
    redis_client = redis.from_url(url, decode_responses=True)
    clear_sync_redis_test_keys(redis_client)
    storage = RedisStorage(redis_client, key_prefix='test:')
    yield storage
    clear_sync_redis_test_keys(redis_client)
    storage.close()


@pytest.fixture
def sync_redis_storage_tls():
    url = os.environ.get('REDIS_TLS_URL')
    if not url:
        pytest.skip('REDIS_TLS_URL not set, skipping TLS tests.')
    redis_client = redis.from_url(url, decode_responses=True)
    clear_sync_redis_test_keys(redis_client)
    storage = RedisStorage(redis_client, key_prefix='test:')
    yield storage
    clear_sync_redis_test_keys(redis_client)
    storage.close()


@pytest.fixture
def storage_fixture(request):
    """Resolve the concrete storage fixture named by indirect parametrization."""
    return request.getfixturevalue(request.param)


# Async Fixture with Mocked Redis Time
@pytest_asyncio.fixture
async def async_redis_storage_with_server_time():
    if not is_redis_available():
        pytest.skip("Redis not available, skipping redis tests.")
    redis_client = await aioredis.from_url(
        "redis://localhost:6379", decode_responses=True
    )
    await clear_async_redis_test_keys(redis_client)
    storage = AsyncRedisStorage(redis_client, use_redis_time=True)

    time_counter = [1000.0]  # start at 1000 seconds

    async def mock_time():
        time_counter[0] += 0.1
        seconds = int(time_counter[0])
        microseconds = int((time_counter[0] - seconds) * 1_000_000)
        return (seconds, microseconds)

    redis_client.time = AsyncMock(side_effect=mock_time)
    yield storage

    await clear_async_redis_test_keys(redis_client)
    await storage.close()


# Sync Fixture with Mocked Redis Time
@pytest.fixture
def sync_redis_storage_with_server_time():
    if not is_redis_available():
        pytest.skip("Redis not available, skipping redis tests.")

    redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
    clear_sync_redis_test_keys(redis_client)
    storage = RedisStorage(redis_client, use_redis_time=True)
    time_counter = [1000.0]

    def mock_time():
        time_counter[0] += 0.1
        seconds = int(time_counter[0])
        microseconds = int((time_counter[0] - seconds) * 1_000_000)
        return (seconds, microseconds)

    redis_client.time = MagicMock(side_effect=mock_time)
    yield storage

    clear_sync_redis_test_keys(redis_client)
    storage.close()
