import threading
from collections import deque
from typing import Dict, Deque, Tuple
from .base_sync import StorageSync
import math

class MemoryStorageSync(StorageSync):
    def __init__(self) -> None:
        self._sliding: Dict[str, Deque[float]] = {}
        self._fixed: Dict[str, Tuple[int, float]] = {}
        self._token: Dict[str, Tuple[float, float]] = {}
        self._leaky: Dict[str, Tuple[int, float]] = {}
        self._key_locks: Dict[str, threading.Lock] = {}
        self._global_lock= threading.Lock()

    def get_lock(self, key: str) -> threading.Lock:
        """Get or create a lock for the given key."""
        if key in self._key_locks:
            return self._key_locks[key]
        with self._global_lock:
            if key not in self._key_locks:
                self._key_locks[key] = threading.Lock()
        return self._key_locks[key]

    def sliding_window(self, key: str, window: int, limit: int, now: float) -> Tuple[bool, int, float]:
        lock = self.get_lock(key)
        with lock:
            q = self._sliding.setdefault(key, deque())

            while q and q[0] < now - window:
                q.popleft()

            if len(q) < limit:
                q.append(now)
                remaining = limit - len(q)
                reset_at = q[0] + window if q else now + window
                return True, remaining, reset_at
            
            else:
                reset_at = q[0] + window
                return False, 0, reset_at
            
    def fixed_window(self, key: str, window: int, limit: int, now: float) -> Tuple[bool, int, float]:
        lock = self.get_lock(key)
        with lock:
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
            
    def token_bucket(self, key: str, capacity: int, refill_rate: float, now: float) -> Tuple[bool, int, float]:
        lock = self.get_lock(key)
        with lock:
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
            
    def leaky_bucket(self, key: str, capacity: int, leak_rate: float, now: float) -> Tuple[bool, int, float]:
        lock = self.get_lock(key)
        with lock:
            queue_size, last_leak_time = self._leaky.get(key, (0, now))

            leaked = math.floor((now - last_leak_time) * leak_rate)
            new_queue = max(queue_size - leaked, 0)

            if new_queue < capacity:
                new_queue += 1
                self._leaky[key] = (new_queue, now)

                remaining = capacity - new_queue
                reset_at = now + (1 / leak_rate)
                return True, remaining, reset_at
            
            else:
                return False, 0, now + (1 / leak_rate)