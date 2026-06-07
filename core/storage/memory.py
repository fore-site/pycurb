import asyncio
from collections import deque
from typing import Dict, Deque, Tuple
from .base import Storage
import math

class MemoryStorage(Storage):
    def __init__(self) -> None:
        self._sliding: Dict[str, Deque[float]] = {}
        self._fixed: Dict[str, Tuple[int, float]] = {}
        self._token: Dict[str, Tuple[float, float]] = {}
        self._leaky: Dict[str, Tuple[int, float]] = {}
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
            # Get or create the deque for this key
            q = self._sliding.setdefault(key, deque())

            # Remove timestamps outside the current window
            while q and q[0] <= now - window:
                q.popleft()

            # Check if we can allow the request
            if len(q) < limit:
                q.append(now)
                remaining = limit - len(q)
                reset_at = q[0] + window if q else now + window
                return True, remaining, reset_at
            
            # Request is not allowed, return when the window resets
            else:
                reset_at = q[0] + window
                return False, 0, reset_at
            
    async def fixed_window(self, key: str, window: int, limit: int, now: float) -> Tuple[bool, int, float]:
        lock = await self.get_lock(key)
        async with lock:
        # Calculate the start of the current window
            computed_window_start = math.floor(now / window) * window

            # Get or create the counter and window start for this key
            count, stored_window_start = self._fixed.get(key, (0, computed_window_start))

            # If we're in a new window, reset the count
            if stored_window_start < computed_window_start:
                count = 0
                stored_window_start = computed_window_start

            # Check if we can allow the request
            if count < limit:
                count += 1
                self._fixed[key] = (count, stored_window_start)
                remaining = limit - count
                reset_at = stored_window_start + window
                return True, remaining, reset_at
            
            # Request is not allowed, return when the next window starts
            else:
                reset_at = stored_window_start + window
                return False, 0, reset_at
            
    async def token_bucket(self, key: str, capacity: int, refill_rate: float, now: float) -> Tuple[bool, int, float]:
        pass