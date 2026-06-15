import asyncio
from collections import deque
from typing import Dict, Deque, Tuple
from .base_async import AsyncStorage
import math

class AsyncMemoryStorage(AsyncStorage):
    """Async in-memory storage for rate limiting."""

    def __init__(self) -> None:
        self._sliding: Dict[str, Deque[float]] = {}
        self._fixed: Dict[str, Tuple[int, float]] = {}
        self._token: Dict[str, Tuple[float, float]] = {}
        self._leaky: Dict[str, Tuple[int, float]] = {}
        self._gcra: Dict[str, float] = {}
        self._key_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock= asyncio.Lock()

    async def get_lock(self, key: str) -> asyncio.Lock:
        """Get or create a lock for the given key."""
        if key in self._key_locks:
            return self._key_locks[key]
        async with self._global_lock:
            if key not in self._key_locks:
                self._key_locks[key] = asyncio.Lock()
        return self._key_locks[key]

    async def sliding_window(self, key: str, window: int, limit: int, now: float) -> Tuple[bool, int, float]:
        lock = await self.get_lock(key)
        async with lock:
            q = self._sliding.setdefault(key, deque())

            while q and q[0] <= now - window:
                q.popleft()

            if len(q) < limit:
                q.append(now)
                remaining = limit - len(q)
                reset_at = q[0] + window if q else now + window
                return True, remaining, reset_at
            
            else:
                reset_at = q[0] + window
                return False, 0, reset_at
            
    async def fixed_window(self, key: str, window: int, limit: int, now: float) -> Tuple[bool, int, float]:
        lock = await self.get_lock(key)
        async with lock:
            computed_window_start = math.floor(now / window) * window

            count, stored_window_start = self._fixed.get(key, (0, computed_window_start))

            if stored_window_start < computed_window_start:
                count = 0
                stored_window_start = computed_window_start

            if count < limit:
                count += 1
                self._fixed[key] = (count, stored_window_start)
                remaining = limit - count
                reset_at = stored_window_start + window
                return True, remaining, reset_at
            
            else:
                reset_at = stored_window_start + window
                return False, 0, reset_at
            
    async def token_bucket(self, key: str, capacity: int, refill_rate: float, now: float) -> Tuple[bool, int, float]:
        lock = await self.get_lock(key)
        async with lock:
            tokens, last_refill_time = self._token.get(key, (float(capacity), now))

            time_elapsed = now - last_refill_time
            tokens_during_elapsed = time_elapsed * refill_rate
            
            new_tokens = min(tokens + tokens_during_elapsed, float(capacity))

            if new_tokens >= 1:
                new_tokens -= 1
                self._token[key] = (new_tokens, now)
                remaining = int(new_tokens)
                reset_at = now + (capacity - new_tokens) / refill_rate
                return True, remaining, reset_at
            
            else:
                reset_at = now + (1 - new_tokens) / refill_rate
                return False, 0, reset_at
            
    async def leaky_bucket(self, key: str, capacity: int, leak_rate: float, now: float) -> Tuple[bool, int, float]:
        lock = await self.get_lock(key)
        async with lock:
            queue_size, last_leak_time = self._leaky.get(key, (0, now))

            leaked = math.floor((now - last_leak_time) * leak_rate)
            new_queue = max(queue_size - leaked, 0)

            # Preserve fractional leak tracking history
            if leaked > 0:
                last_leak_time += leaked / leak_rate

            if new_queue < capacity:
                new_queue += 1
                self._leaky[key] = (new_queue, last_leak_time)

                remaining = capacity - new_queue
                reset_at = now + (1 / leak_rate)
                return True, remaining, reset_at
            
            else:
                return False, 0, now + (1 / leak_rate)

    async def gcra(self, key: str, capacity: int, rate: float, now: float) -> Tuple[bool, int, float]:
        lock = await self.get_lock(key)
        async with lock:
            tat = self._gcra.get(key, now)  # default first request

            interval = 1.0 / rate
            # Use (capacity - 1) so 'capacity' exactly equals max burst size
            burst_interval = (capacity - 1) * interval 

            # Allowed if TAT is within allowed burst window
            allowed = tat <= now + burst_interval

            if allowed:
                new_tat = max(tat, now) + interval
                self._gcra[key] = new_tat

                # Number of scheduled intervals after this request
                used_intervals = (new_tat - now) * rate
                remaining = max(0, int(math.floor(capacity - used_intervals)))

                # The bucket is completely empty/reset when new_tat is reached
                reset_at = new_tat
            else:
                remaining = 0
                # True retry time: when tat falls back down into the allowed burst window
                # tat <= t' + burst_interval  ->  t' = tat - burst_interval
                reset_at = tat - burst_interval

            return (allowed, remaining, reset_at)

    async def close(self) -> None:
        return None
