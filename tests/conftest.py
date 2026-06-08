import pytest
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
    
# Async fixtures

@pytest.fixture
async def async_memory_storage():
    return MemoryStorage

@pytest.fixture
async def async_redis_storage():
    if not is_redis_available():
        pytest.skip("Redis not available, skipping redis tests.")
    redis_client = await aioredis.from_url("redis://localhost:6379", decode_responses=True)
    storage = RedisStorage(redis_client, key_prefix="test:")
    yield storage
    await storage.close()

# Sync fixtures

@pytest.fixture
def sync_memory_storage():
    return MemoryStorageSync

@pytest.fixture
def sync_redis_storage():
    if not is_redis_available():
        pytest.skip("Redis not available, skipping redis tests.")
    redis_client = redis.from_url("redis://localhost:6379", decode_responses=True)
    storage = RedisStorageSync(redis_client, key_prefix="test:")
    yield storage
    storage.close()

async_storage_fixtures = ["async_memory_storage", "async_redis_storage"]
sync_storage_fixtures = ["sync_memory_storage", "sync_redis_storage"]