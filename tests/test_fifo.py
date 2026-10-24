"""Tests for FIFOCache."""

import time
from cacheforge.fifo import FIFOCache


def test_fifo_basic_ops():
    cache = FIFOCache(maxsize=3)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    assert cache.get("a") == 1
    assert cache.get("b") == 2
    assert cache.get("c") == 3
    assert len(cache) == 3


def test_fifo_eviction_strictly_chronological():
    cache = FIFOCache(maxsize=3)
    cache.set("first", 1)
    cache.set("second", 2)
    cache.set("third", 3)

    # In FIFO, reading "first" must NOT prevent it from being evicted next!
    cache.get("first")
    cache.get("first")

    # Add 4th item, "first" must be evicted
    cache.set("fourth", 4)

    assert cache.get("first") is None
    assert cache.get("second") == 2
    assert cache.get("third") == 3
    assert cache.get("fourth") == 4


def test_fifo_ttl():
    cache = FIFOCache(maxsize=5, default_ttl=0.05)
    cache.set("a", 10)
    assert cache.get("a") == 10

    time.sleep(0.08)
    assert cache.get("a") is None
    assert len(cache) == 0
