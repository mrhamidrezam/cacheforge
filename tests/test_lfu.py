"""Tests for LFUCache."""

import time
import pytest
from cacheforge.lfu import LFUCache


def test_lfu_basic_ops():
    cache = LFUCache(maxsize=3)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    assert cache.get("a") == 1
    assert cache.get("b") == 2
    assert cache.get("c") == 3
    assert len(cache) == 3


def test_lfu_eviction_by_frequency():
    cache = LFUCache(maxsize=3)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    # Touch 'a' and 'b' multiple times
    cache.get("a")
    cache.get("a")
    cache.get("b")

    # Frequencies: a=3, b=2, c=1.
    # Inserting 'd' should evict 'c' (frequency=1)
    cache.set("d", 4)

    assert cache.get("c") is None
    assert cache.get("a") == 1
    assert cache.get("b") == 2
    assert cache.get("d") == 4


def test_lfu_lru_tie_breaker():
    cache = LFUCache(maxsize=2)
    # Both 'a' and 'b' will have frequency=1 initially
    cache.set("a", 10)
    cache.set("b", 20)

    # Both have frequency=1, but 'a' was added earlier (LRU among freq=1)
    # Inserting 'c' should evict 'a'
    cache.set("c", 30)

    assert cache.get("a") is None
    assert cache.get("b") == 20
    assert cache.get("c") == 30


def test_lfu_update_increments_freq():
    cache = LFUCache(maxsize=2)
    cache.set("a", 1)
    cache.set("b", 2)

    # Overwrite 'a'
    cache.set("a", 100)

    # Now 'a' has higher frequency than 'b'
    cache.set("c", 3)  # Evicts 'b'

    assert cache.get("b") is None
    assert cache.get("a") == 100
    assert cache.get("c") == 3


def test_lfu_ttl_expiration():
    cache = LFUCache(maxsize=5, default_ttl=0.05)
    cache.set("key", "val")
    assert cache.get("key") == "val"

    time.sleep(0.08)
    assert cache.get("key") is None
    assert len(cache) == 0


def test_lfu_frequency_lookup():
    cache = LFUCache(maxsize=5)
    cache.set("item", 10)
    assert cache.frequency("item") == 1
    cache.get("item")
    assert cache.frequency("item") == 2
    assert cache.frequency("unknown") is None


def test_lfu_invalid_maxsize():
    with pytest.raises(ValueError):
        LFUCache(maxsize=0)
    with pytest.raises(ValueError):
        LFUCache(maxsize=-1)
