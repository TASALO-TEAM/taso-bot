# tests/test_cache.py
"""Tests for SimpleCache with TTL expiration."""
import time
import pytest

from src.cache import SimpleCache


class TestSimpleCache:
    """Test suite for SimpleCache."""

    def test_set_and_get(self):
        """Should store and retrieve values."""
        cache = SimpleCache()
        cache.set("test", {"key": "value"})
        assert cache.get("test") == {"key": "value"}

    def test_get_missing_key(self):
        """Should return None for missing keys."""
        cache = SimpleCache()
        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self):
        """Should expire entries after TTL."""
        cache = SimpleCache()
        cache.set("test", "value")

        # Manually expire by setting old timestamp
        cache._store["test"] = ("value", time.time() - 100)

        assert cache.get("test", ttl=60) is None

    def test_ttl_respects_custom_ttl(self):
        """Should use custom TTL when provided."""
        cache = SimpleCache()
        cache.set("test", "value")

        # Entry should be valid with short TTL
        assert cache.get("test", ttl=120) == "value"

    def test_overwrite_value(self):
        """Should overwrite existing values."""
        cache = SimpleCache()
        cache.set("test", "first")
        cache.set("test", "second")
        assert cache.get("test") == "second"

    def test_clear(self):
        """Should clear all cached values."""
        cache = SimpleCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)

        cache.clear()

        assert cache.get("a") is None
        assert cache.get("b") is None
        assert cache.get("c") is None

    def test_size(self):
        """Should return correct cache size."""
        cache = SimpleCache()
        assert cache.size() == 0

        cache.set("a", 1)
        cache.set("b", 2)
        assert cache.size() == 2

    def test_multiple_keys(self):
        """Should handle multiple independent keys."""
        cache = SimpleCache()
        cache.set("rates", {"USD": 515.0})
        cache.set("sources", ["eltoque", "cadeca"])

        assert cache.get("rates")["USD"] == 515.0
        assert len(cache.get("sources")) == 2

    def test_expiration_does_not_affect_other_keys(self):
        """Expiring one key should not affect others."""
        cache = SimpleCache()
        cache.set("a", 1)
        cache.set("b", 2)

        # Expire key "a"
        cache._store["a"] = (1, time.time() - 100)

        assert cache.get("a", ttl=60) is None
        assert cache.get("b") == 2

    def test_global_cache_instance(self):
        """Global cache instance should be importable."""
        from src.cache import cache

        assert isinstance(cache, SimpleCache)
        assert cache.size() == 0  # Fresh instance
