# src/cache.py
"""Simple in-memory cache with TTL for bot API responses.

Provides a lightweight caching layer to reduce API calls when multiple
users request the same data within a short time window.
"""
import time
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


class SimpleCache:
    """In-memory cache with TTL (time-to-live) expiration."""

    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}
        self._hits = 0
        self._misses = 0
        self._sets = 0
        self._expires = 0

    def get(self, key: str, ttl: int = 60) -> Any | None:
        """Get value from cache if not expired.

        Args:
            key: Cache key
            ttl: Time-to-live in seconds (default: 60)

        Returns:
            Cached value or None if expired/missing
        """
        if key not in self._store:
            self._misses += 1
            logger.info("📦 Cache GET '%s' - MISS", key)
            return None

        value, stored_at = self._store[key]
        age = time.time() - stored_at

        if age > ttl:
            del self._store[key]
            self._misses += 1
            self._expires += 1
            logger.info("📦 Cache GET '%s' - MISS (expired, age=%ds > ttl=%ds)", key, int(age), ttl)
            return None

        self._hits += 1
        logger.debug("📦 Cache GET '%s' - HIT (age=%ds, ttl=%ds)", key, int(age), ttl)
        return value

    def set(self, key: str, value: Any) -> None:
        """Set value in cache with current timestamp.

        Args:
            key: Cache key
            value: Value to cache
        """
        try:
            data_size = sys.getsizeof(value)
        except (TypeError, RecursionError):
            data_size = -1

        self._store[key] = (value, time.time())
        self._sets += 1
        logger.debug("📦 Cache SET '%s' (size=%d bytes, total_keys=%d)", key, data_size, len(self._store))

    def clear(self) -> None:
        """Clear all cached values."""
        count = len(self._store)
        self._store.clear()
        logger.info("📦 Cache CLEAR - %d keys removed", count)

    def invalidate(self, key: str) -> bool:
        """Remove a specific key from cache.

        Args:
            key: Cache key to remove

        Returns:
            True if key was found and removed, False otherwise
        """
        if key in self._store:
            del self._store[key]
            logger.debug("📦 Cache INVALIDATE '%s'", key)
            return True
        logger.debug("📦 Cache INVALIDATE '%s' - key not found", key)
        return False

    def size(self) -> int:
        """Return number of cached entries (including expired)."""
        return len(self._store)

    def get_stats(self) -> dict:
        """Return cache statistics for monitoring.

        Returns:
            Dictionary with cache metrics
        """
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0

        stats = {
            "keys_in_store": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "sets": self._sets,
            "expires": self._expires,
            "hit_rate_pct": round(hit_rate, 2),
        }

        logger.debug(
            "📦 Cache STATS - keys=%d, hits=%d, misses=%d, sets=%d, expires=%d, hit_rate=%.1f%%",
            stats["keys_in_store"],
            stats["hits"],
            stats["misses"],
            stats["sets"],
            stats["expires"],
            stats["hit_rate_pct"],
        )

        return stats


# Global cache instance shared across the bot
cache = SimpleCache()
