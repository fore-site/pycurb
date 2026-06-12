from abc import ABC, abstractmethod
from typing import Tuple

class AsyncStorage(ABC):
    """Abstract storage backend for rate limiter counters. Asynchronous version (WSGI compatible)"""

    @abstractmethod
    async def sliding_window(
        self, key: str, window: int, limit: int, now: float
    ) -> Tuple[bool, int, float]:
        """
        Record a request using sliding window algorithm.

        Args:
            key: Unique identifier.
            window: Time window in seconds.
            limit: Maximum allowed requests per window.
            now: Current Unix timestamp (seconds).

        Returns:
            Tuple (allowed, remaining, reset_at)
            - allowed: bool - True if request within limit.
            - remaining: int - Remaining requests allowed in current window.
            - reset_at: float - Unix timestamp when the window expires (oldest request + window).
        """
        pass

    @abstractmethod
    async def fixed_window(
        self, key: str, window: int, limit: int, now: float
    ) -> Tuple[bool, int, float]:
        """
        Record a request using fixed window algorithm.

        The window is aligned to calendar boundaries: e.g., window=60 means
        windows start at timestamps 0, 60, 120, ... (floor(now / window) * window).

        Args:
            key: Unique identifier.
            window: Window size in seconds.
            limit: Maximum requests per window.
            now: Current Unix timestamp (seconds).

        Returns:
            Tuple (allowed, remaining, reset_at)
            - allowed: bool - True if request within limit.
            - remaining: int - Remaining requests allowed in current window.
            - reset_at: start of next window (aligned).
        """
        pass

    @abstractmethod
    async def token_bucket(
        self, key: str, capacity: int, refill_rate: float, now: float
    ) -> Tuple[bool, int, float]:
        """
        Consume one token from a token bucket.

        Args:
            key: Unique identifier.
            capacity: Maximum tokens (burst limit).
            refill_rate: Tokens added per second.
            now: Current Unix timestamp (seconds).

        Returns:
            (allowed, remaining_tokens, reset_at)
            - allowed: True if a token was available.
            - remaining_tokens: Tokens left after consumption (or current tokens if not allowed).
            - reset_at: Timestamp when next token will be added (if not allowed) or when bucket would be full (optional). Usually used for Retry-After.
        """
        pass

    @abstractmethod
    async def leaky_bucket(
        self, key: str, capacity: int, leak_rate: float, now: float
    ) -> Tuple[bool, int, float]:
        """
        Process a request through a leaky bucket.

        The bucket has a capacity (queue size). Requests leak out at leak_rate per second.
        If the bucket is full, request is denied.

        Args:
            key: Unique identifier.
            capacity: Maximum queue size.
            leak_rate: Requests processed per second (leak rate).
            now: Current Unix timestamp (seconds).

        Returns:
            (allowed, remaining_capacity, reset_at)
            - allowed: True if request can be enqueued.
            - remaining_capacity: Slots left in the queue.
            - reset_at: Timestamp when the next request can be processed (if full).
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Release any resources (connections, etc.)."""
        pass