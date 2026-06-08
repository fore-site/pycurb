import pytest
import pytest_asyncio
import redis
import redis.asyncio as aioredis
from ..core.storage.memory import MemoryStorage
from ..core.storage.memory_sync import MemoryStorageSync
from ..core.storage.redis import RedisStorage
from ..core.storage.redis_sync import RedisStorageSync

def is_redis_available(host='localhost', port=6379):
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
    storage = MemoryStorage()
    yield storage
    await storage.close()

@pytest_asyncio.fixture
async def async_redis_storage():
    if not is_redis_available():
        pytest.skip("Redis not available, skipping redis tests.")
    redis_client = aioredis.from_url("redis://localhost:6379", decode_responses=True)
    await clear_async_redis_test_keys(redis_client)
    storage = RedisStorage(redis_client, key_prefix="test:")
    yield storage
    await clear_async_redis_test_keys(redis_client)
    await storage.close()

# Sync fixtures

@pytest.fixture
def sync_memory_storage():
    storage = MemoryStorageSync()
    yield storage
    storage.close()

@pytest.fixture
def sync_redis_storage():
    if not is_redis_available():
        pytest.skip("Redis not available, skipping redis tests.")
    redis_client = redis.from_url("redis://localhost:6379", decode_responses=True)
    clear_sync_redis_test_keys(redis_client)
    storage = RedisStorageSync(redis_client, key_prefix="test:")
    yield storage
    clear_sync_redis_test_keys(redis_client)
    storage.close()


@pytest.fixture
def storage_fixture(request):
    """Resolve the concrete storage fixture named by indirect parametrization."""
    return request.getfixturevalue(request.param)
