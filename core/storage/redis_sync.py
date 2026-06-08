import math
import binascii
import os
from typing import Tuple
import redis
from .base_sync import StorageSync

class RedisStorageSync(StorageSync):
    """Sync redis storage for rate limiting."""
    
    def __init__(self, redis_client: redis.Redis, key_prefix: str = "ratelimit:") -> None:
        self.redis = redis_client
        self.prefix = key_prefix

    def sliding_window(self, key: str, window: int, limit: int, now: float) -> Tuple[bool, int, float]:
        # Lua script for sliding window using sorted.
        lua_script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local window = tonumber(ARGV[2])
        local limit = tonumber(ARGV[3])
        local unique_id = ARGV[4]

        -- Remove expired entries
        local max_cutoff = '(' .. (now - window)
        redis.call('ZREMRANGEBYSCORE', key, '-inf', max_cutoff)

        local current = redis.call('ZCARD', key)
        if current < limit then
            redis.call('ZADD', key, now, now .. ':' .. unique_id)
            redis.call('EXPIRE', key, window)
            return {1, limit - current - 1, now + window}
        else
            local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
            local reset_at = tonumber(oldest[2]) + window
            return {0, 0, reset_at}
        end
        """
        unique_id = binascii.hexlify(os.urandom(8)).decode()
        script = self.redis.register_script(lua_script)
        full_key = self.prefix + "sliding:" + key
        result = script(keys=[full_key], args=[now, window, limit, unique_id])
        allowed = bool(result[0])
        remaining = int(result[1])
        reset_at = float(result[2])

        return allowed, remaining, reset_at

    def fixed_window(self, key: str, window: int, limit: int, now: float) -> Tuple[bool, int, float]:
        window_start = math.floor(now / window) * window
        window_key = f"{self.prefix}fixed:{key}:{window_start}"

        # Atomic increment
        count = self.redis.incr(window_key)
        # Set expiry
        if count == 1:
            self.redis.expire(window_key, window)
        if count > limit:
            reset_at = window_start + window
            return False, 0, reset_at
        else:
            remaining = limit - count
            reset_at = window_start + window
            return True, remaining, reset_at
        
    def token_bucket(self, key: str, capacity: int, refill_rate: float, now: float) -> Tuple[bool, int, float]:
        # Lua script for token bucket
        lua_script = """
        local key = KEYS[1]
        local capacity = tonumber(ARGV[1])
        local rate = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])

        local data = redis.call('GET', key)
        local tokens, last_refill
        if data then
            local colon = string.find(data, ':')
            if colon then
                tokens = tonumber(string.sub(data, 1, colon - 1)) 
                last_refill = tonumber(string.sub(data, colon + 1))
            else
                tokens = capacity
                last_refill = now
            end
        else
            tokens = capacity
            last_refill = now
        end

        local elapsed = now - last_refill
        local tokens_during_elapsed = elapsed * rate
        local new_tokens = math.min(capacity, tokens + tokens_during_elapsed)

        if new_tokens >= 1 then
            new_tokens = new_tokens - 1
            redis.call('SET', key, new_tokens .. ':' .. now)
            redis.call('EXPIRE', key, 3600) -- optional expiry
            local remaining = math.floor(new_tokens)
            local reset_at = now + (capacity - new_tokens) / rate
            return {1, remaining, reset_at}
        else
            local wait = (1 - new_tokens) / rate
            local reset_at = now + wait
            return {0, 0, reset_at}
        end
        """
        script = self.redis.register_script(lua_script)
        full_key = self.prefix + "token:" + key
        result = script(keys=[full_key], args=[capacity, refill_rate, now])
        allowed = bool(result[0])
        remaining = int(result[1])
        reset_at = float(result[2])

        return allowed, remaining, reset_at

    def leaky_bucket(self, key: str, capacity: int, leak_rate: float, now: float) -> Tuple[bool, int, float]:
        # Lua script for leaky bucket (counter variant)
        lua_script = """
        local key = KEYS[1]
        local capacity = tonumber(ARGV[1])
        local rate = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])

        local data = redis.call('GET', key)
        local queue_size, last_leak
        if data then
            local colon = string.find(data, ':')
            if colon then
                queue_size = tonumber(string.sub(data, 1, colon - 1))
                last_leak = tonumber(string.sub(data, colon + 1))
            else
                queue_size = 0
                last_leak = now
            end
        else
            queue_size = 0
            last_leak = now
        end

        local elapsed = now - last_leak
        local leaked = math.floor(elapsed * rate)
        local new_queue = math.max(queue_size - leaked, 0)

        -- Preserve fractinal leak tracking history
        if leaked > 0 then
            last_leak = last_leak + (leaked / rate)
        end

        if new_queue < capacity then
            new_queue = new_queue + 1
            redis.call('SET', key, new_queue .. ':' .. last_leak)
            redis.call('EXPIRE', key, 3600)
            local remaining = capacity - new_queue
            local reset_at = now + (1 / rate)
            return {1, remaining, reset_at}
        else
            local reset_at = now + (1 / rate)
            return {0, 0, reset_at}
        end
        """
        script = self.redis.register_script(lua_script)
        full_key = self.prefix + 'leaky:' + key
        result = script(keys=[full_key], args=[capacity, leak_rate, now])
        allowed = bool(result[0])
        remaining = int(result[1])
        reset_at = float(result[2])

        return allowed, remaining, reset_at
    
    def close(self) -> None:
        self.redis.close()