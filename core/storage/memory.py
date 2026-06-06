import asyncio
from collections import deque
from typing import Dict, Deque, Tuple
from .base import Storage

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
            if key not in self._sliding:
                self._sliding[key] = deque()
            q = self._sliding[key]
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) < limit:
                q.append(now)
                return True, limit - len(q), (q[0] + window if q else now + window)
            else:
                return False, 0, (q[0] + window)