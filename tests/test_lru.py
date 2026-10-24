"""Tests for LRUCache."""

import time
import pytest
from cacheforge.lru import LRUCache


def test_lru_basic_ops():
    cache = LRUCache(maxsize=3)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    assert cache.get("a") == 1
    assert cache.get("b") == 2
    assert cache.get("c") == 3
    assert len(cache) == 3
    assert "a" in cache
    assert "d" not in cache
    assert cache.get("d") is None
    assert cache.get("d", "default") == "default"


def test_lru_eviction_order():
    cache = LRUCache(maxsize=3)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    # Access 'a' so 'b' becomes least recently used
    assert cache.get("a") == 1

    # Insert 'd', should evict 'b'
    cache.set("d", 4)

    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3
    assert cache.get("d") == 4
    assert len(cache) == 3


def test_lru_update_existing():
    cache = LRUCache(maxsize=2)
    cache.set("x", 10)
    cache.set("y", 20)
    cache.set("x", 100)  # Updates value and moves to MRU

    cache.set("z", 30)  # Should evict 'y', keeping 'x'

    assert cache.get("x") == 100
    assert cache.get("y") is None
    assert cache.get("z") == 30


def test_lru_ttl_expiration():
    cache = LRUCache(maxsize=5, default_ttl=0.05)
    cache.set("temp", "hello")
    assert cache.get("temp") == "hello"

    time.sleep(0.08)
    assert cache.get("temp") is None
    assert "temp" not in cache


def test_lru_cost_eviction():
    cache = LRUCache(maxsize=10, max_cost=10)
    cache.set("small1", 1, cost=3)
    cache.set("small2", 2, cost=4)
    assert cache.current_cost == 7

    # Adding large item should evict small1 to keep cost <= 10
    cache.set("large", 3, cost=5)
    assert cache.current_cost <= 10
    assert cache.get("small1") is None
    assert cache.get("small2") == 2
    assert cache.get("large") == 3


def test_lru_peek():
    cache = LRUCache(maxsize=2)
    cache.set("a", 1)
    cache.set("b", 2)

    # peek does not reorder
    assert cache.peek("a") == 1
    cache.set("c", 3)  # 'a' was still LRU, so 'a' should be evicted

    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_lru_dict_interface():
    cache = LRUCache(maxsize=5)
    cache["key1"] = "val1"
    assert cache["key1"] == "val1"
    assert "key1" in cache

    with pytest.raises(KeyError):
        _ = cache["nonexistent"]

    del cache["key1"]
    assert "key1" not in cache

    with pytest.raises(KeyError):
        del cache["nonexistent"]


def test_lru_pop_and_get_or_set():
    cache = LRUCache(maxsize=5)
    cache.set("item", 42)
    assert cache.pop("item") == 42
    assert cache.pop("item", "def") == "def"

    call_count = 0

    def compute():
        nonlocal call_count
        call_count += 1
        return "computed"

    res1 = cache.get_or_set("k", compute)
    res2 = cache.get_or_set("k", compute)

    assert res1 == "computed"
    assert res2 == "computed"
    assert call_count == 1


def test_lru_callbacks():
    hits = []
    misses = []
    evictions = []

    cache = LRUCache(
        maxsize=2,
        on_hit=lambda k, v: hits.append((k, v)),
        on_miss=lambda k: misses.append(k),
        on_evict=lambda k, v: evictions.append((k, v)),
    )

    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")
    cache.get("missing")
    cache.set("c", 3)  # Evicts 'b'

    assert hits == [("a", 1)]
    assert misses == ["missing"]
    assert evictions == [("b", 2)]


def test_lru_keys_values_items_and_clear():
    cache = LRUCache(maxsize=3)
    cache.set("x", 1)
    cache.set("y", 2)

    assert sorted(cache.keys()) == ["x", "y"]
    assert sorted(cache.values()) == [1, 2]
    assert sorted(cache.items()) == [("x", 1), ("y", 2)]

    cache.clear()
    assert len(cache) == 0
    assert cache.keys() == []
