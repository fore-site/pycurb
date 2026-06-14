import functools
import math
import binascii
import os
from typing import Tuple, Optional
import redis
import redis.exceptions as redis_exceptions
import logging
from .base import Storage

logger = logging.getLogger(__name__)

def with_fallback(func):
    """Decorator to handle Redis exceptions and fallback to another storage or fail-open/closed."""
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except (
            redis_exceptions.ConnectionError,
            redis_exceptions.TimeoutError,
            redis_exceptions.ResponseError,
            redis_exceptions.ReadOnlyError,
        ) as e:
            logger.warning(f"Redis operation {func.__name__} failed: {e}")
            if self.fallback_storage is not None:
                logger.warning(f"Redis error: {e}. Falling back to {self.fallback_storage.__class__.__name__}.")
                # Call the same method on fallback storage (sync)
                fallback_method = getattr(self.fallback_storage, func.__name__)
                return fallback_method(*args, **kwargs)

            # Determine 'now' from args/kwargs if present (last positional arg is expected to be `now`)
            now = kwargs.get('now') if 'now' in kwargs else (args[-1] if args else None)

            if self.fail_open:
                logger.warning(f"Redis error: {e}. Fail-open enabled, allowing request.")
                try:
                    reset_at = float(now) + 3600 if now is not None else float('inf')
                except Exception:
                    reset_at = float('inf')
                # Provide a large remaining default so callers can proceed conservatively
                return True, 9999, reset_at
            else:
                logger.warning(f"Redis error: {e}. Fail-closed enabled, denying request.")
                return False, 0, float('inf')

    return wrapper

class RedisStorage(Storage):
    """Redis storage for rate limiting."""
    
    def __init__(self, 
                 redis_client: redis.Redis, 
                 key_prefix: str = "ratelimit:",
                 use_redis_time: bool = False,
                 fallback_storage: Optional[Storage] = None,
                 fail_open: bool = False
                 ) -> None:
        self.redis = redis_client
        self.prefix = key_prefix
        self.use_redis_time = use_redis_time
        self.fallback_storage = fallback_storage
        self.fail_open = fail_open

    @with_fallback
    def sliding_window(self, key: str, window: int, limit: int, now: float) -> Tuple[bool, int, float]:
        # Lua script for sliding window using sorted.
        lua_script = """
        local key = KEYS[1]
        local now = ARGV[1]

        if now == 'server' then
            local time_parts = redis.call('TIME');
            now = tonumber(time_parts[1]) + tonumber(time_parts[2]) / 1000000
        else
            now = tonumber(now)
        end

        local window = tonumber(ARGV[2])
        local limit = tonumber(ARGV[3])
        local unique_id = ARGV[4]

        -- Remove expired entries
        local max_cutoff = now - window
        redis.call('ZREMRANGEBYSCORE', key, '-inf', max_cutoff)

        local current = redis.call('ZCARD', key)
        if current < limit then
            redis.call('ZADD', key, now, now .. ':' .. unique_id)
            redis.call('EXPIRE', key, window)
            return {1, limit - current - 1, string.format('%.17g', now + window)}
        else
            local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
            local reset_at = tonumber(oldest[2]) + window
            return {0, 0, string.format('%.17g', reset_at)}
        end
        """
        unique_id = binascii.hexlify(os.urandom(8)).decode()
        script = self.redis.register_script(lua_script)
        full_key = self.prefix + "sliding:" + key

        if self.use_redis_time:
            result = script(keys=[full_key], args=["server", window, limit, unique_id])
        else:
            result = script(keys=[full_key], args=[now, window, limit, unique_id])
        
        allowed = bool(result[0])
        remaining = int(result[1])
        reset_at = float(result[2])

        return allowed, remaining, reset_at

    @with_fallback
    def fixed_window(self, key: str, window: int, limit: int, now: float) -> Tuple[bool, int, float]:
        if self.use_redis_time:
            time_parts = self.redis.time()
            now = time_parts[0] + time_parts[1] / 1_000_000 
        
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
        
    @with_fallback
    def token_bucket(self, key: str, capacity: int, refill_rate: float, now: float) -> Tuple[bool, int, float]:
        # Lua script for token bucket
        lua_script = """
        local key = KEYS[1]
        local now = ARGV[1]

        if now == 'server' then
            local time_parts = redis.call('TIME');
            now = tonumber(time_parts[1]) + tonumber(time_parts[2]) / 1000000
        else
            now = tonumber(now)
        end

        local capacity = tonumber(ARGV[2])
        local rate = tonumber(ARGV[3])

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
            return {1, remaining, string.format('%.17g', reset_at)}
        else
            local wait = (1 - new_tokens) / rate
            local reset_at = now + wait
            return {0, 0, string.format('%.17g', reset_at)}
        end
        """
        script = self.redis.register_script(lua_script)
        full_key = self.prefix + "token:" + key

        if self.use_redis_time:
            result = script(keys=[full_key], args=["server", capacity, refill_rate])
        else:
            result = script(keys=[full_key], args=[now, capacity, refill_rate])
        allowed = bool(result[0])
        remaining = int(result[1])
        reset_at = float(result[2])

        return allowed, remaining, reset_at

    @with_fallback
    def leaky_bucket(self, key: str, capacity: int, leak_rate: float, now: float) -> Tuple[bool, int, float]:
        # Lua script for leaky bucket (counter variant)
        lua_script = """
        local key = KEYS[1]
        local now = ARGV[1]

        if now == 'server' then
            local time_parts = redis.call('TIME');
            now = tonumber(time_parts[1]) + tonumber(time_parts[2]) / 1000000
        else
            now = tonumber(now)
        end

        local capacity = tonumber(ARGV[2])
        local rate = tonumber(ARGV[3])

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
            return {1, remaining, string.format('%.17g', reset_at)}
        else
            local reset_at = now + (1 / rate)
            return {0, 0, string.format('%.17g', reset_at)}
        end
        """
        script = self.redis.register_script(lua_script)
        full_key = self.prefix + 'leaky:' + key

        if self.use_redis_time:
            result = script(keys=[full_key], args=["server", capacity, leak_rate])
        else:
            result = script(keys=[full_key], args=[now, capacity, leak_rate])
        
        allowed = bool(result[0])
        remaining = int(result[1])
        reset_at = float(result[2])

        return allowed, remaining, reset_at

    def gcra(self, key: str, capacity: int, rate: float, now: float) -> Tuple[bool, int, float]:
        lua_script = """
        local key = KEYS[1]
        local now = ARGV[1]
        
        if now == 'server' then
            local time_parts = redis.call('TIME');
            now = tonumber(time_parts[1]) + tonumber(time_parts[2]) / 1000000
        else
            now = tonumber(now)
        end

        local rate = tonumber(ARGV[2])
        local capacity = tonumber(ARGV[3])

        local interval = 1.0 / rate
        local burst_interval = capacity * interval

        local tat_str = redis.call('GET', key)
        local tat
        
        if tat_str then
            tat = tonumber(tat_str)
        else
            tat = now
        end
        
        local allowed = (tat < now + burst_interval)
        local new_tat
        local remaining
        local reset_at

        if allowed then
            new_tat = math.max(tat, now) + interval
            local ttl_ms = math.max(1, math.ceil((new_tat - now + interval) * 1000))
            redis.call('SET', key, new_tat)
            redis.call('PEXPIRE', key, ttl_ms)
            local used_intervals = (new_tat - now) * rate
            remaining = math.max(0, math.floor(capacity - used_intervals))
            reset_at = new_tat
        else
            remaining = 0
            reset_at = tat - burst_interval
        end

        return {allowed and 1 or 0, remaining, reset_at}
        """

        script = self.redis.register_script(lua_script)
        full_key = self.prefix + "gcra:" + key

        if self.use_redis_time:
            result = script(keys=[full_key], args=["server", rate, capacity])
        else:
            result = script(keys=[full_key], args=[now, rate, capacity])

        allowed = bool(result[0])
        remaining = int(result[1])
        reset_at = float(result[2])

        return (allowed, remaining, reset_at)
    
    def close(self) -> None:
        self.redis.close()
