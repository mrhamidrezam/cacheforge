"""Tests for TTLCache and SlidingTTLCache."""

import time
import pytest
from cacheforge.ttl import SlidingTTLCache, TTLCache


def test_ttl_basic_expiration():
    cache = TTLCache(default_ttl=0.06, maxsize=10)
    cache.set("a", 1)
    cache.set("b", 2, ttl=0.2)

    assert cache.get("a") == 1
    assert cache.get("b") == 2

    time.sleep(0.08)

    # 'a' should be expired, 'b' still valid
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.ttl_remaining("b") is not None
    assert cache.ttl_remaining("b") > 0.0
    assert cache.ttl_remaining("a") is None


def test_ttl_manual_prune():
    cache = TTLCache(default_ttl=0.05, maxsize=10)
    cache.set("x", 1)
    cache.set("y", 2)

    time.sleep(0.07)
    pruned = cache.prune_expired()
    assert pruned == 2
    assert len(cache) == 0


def test_ttl_capacity_evicts_earliest_expiring():
    cache = TTLCache(default_ttl=10.0, maxsize=2)
    cache.set("short", 1, ttl=2.0)
    cache.set("long", 2, ttl=100.0)

    # Capacity reached (2/2)
    # Inserting third item will evict "short" because its expires_at is closest
    cache.set("new", 3, ttl=50.0)

    assert cache.get("short") is None
    assert cache.get("long") == 2
    assert cache.get("new") == 3


def test_sliding_ttl_extends_on_read():
    cache = SlidingTTLCache(default_ttl=0.08, maxsize=10)
    cache.set("session", "user_123")

    # Read every 0.05s to keep it alive
    for _ in range(3):
        time.sleep(0.05)
        assert cache.get("session") == "user_123"

    # Stop reading and let it expire
    time.sleep(0.12)
    assert cache.get("session") is None


def test_ttl_invalid_args():
    with pytest.raises(ValueError):
        TTLCache(default_ttl=0)
    with pytest.raises(ValueError):
        TTLCache(default_ttl=-5)
    cache = TTLCache(default_ttl=10)
    with pytest.raises(ValueError):
        cache.set("k", "v", ttl=0)
