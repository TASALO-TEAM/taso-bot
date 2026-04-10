# src/cache.py
"""Simple in-memory cache with TTL for bot API responses.

Provides a lightweight caching layer to reduce API calls when multiple
users request the same data within a short time window.
"""
import time
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SimpleCache:
    """In-memory cache with TTL (time-to-live) expiration."""

    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str, ttl: int = 60) -> Any | None:
        """Get value from cache if not expired.

        Args:
            key: Cache key
            ttl: Time-to-live in seconds (default: 60)

        Returns:
            Cached value or None if expired/missing
        """
        if key not in self._store:
            return None
        value, stored_at = self._store[key]
        if time.time() - stored_at > ttl:
            del self._store[key]
            logger.debug(f"Cache expired: {key}")
            return None
        logger.debug(f"Cache hit: {key}")
        return value

    def set(self, key: str, value: Any) -> None:
        """Set value in cache with current timestamp.

        Args:
            key: Cache key
            value: Value to cache
        """
        self._store[key] = (value, time.time())
        logger.debug(f"Cache set: {key}")

    def clear(self) -> None:
        """Clear all cached values."""
        count = len(self._store)
        self._store.clear()
        logger.debug(f"Cache cleared: {count} entries removed")

    def size(self) -> int:
        """Return number of cached entries (including expired)."""
        return len(self._store)


# Global cache instance shared across the bot
cache = SimpleCache()
