"""Tests for TieredCache."""

from cacheforge.disk import DiskCache
from cacheforge.lru import LRUCache
from cacheforge.tiered import TieredCache


def test_tiered_cache_l1_hit():
    l1 = LRUCache(maxsize=10)
    l2 = LRUCache(maxsize=100)
    tiered = TieredCache(l1=l1, l2=l2)

    tiered.set("key", "val")
    assert tiered.get("key") == "val"
    assert l1.metrics.hits == 1
    assert l2.metrics.hits == 0


def test_tiered_cache_l2_hit_and_promotion(tmp_path):
    l1 = LRUCache(maxsize=2)
    l2 = DiskCache(directory=tmp_path)
    tiered = TieredCache(l1=l1, l2=l2)

    tiered.set("a", 1)
    tiered.set("b", 2)
    tiered.set("c", 3)

    # In L1 (size=2), 'a' was evicted from L1, but remains safely stored in L2!
    assert "a" not in l1
    assert "a" in l2

    # Reading 'a' through TieredCache retrieves from L2 and promotes to L1
    val = tiered.get("a")
    assert val == 1
    assert "a" in l1

    l2.close()


def test_tiered_cache_delete_and_clear():
    l1 = LRUCache(maxsize=10)
    l2 = LRUCache(maxsize=100)
    tiered = TieredCache(l1=l1, l2=l2)

    tiered.set("k1", 100)
    assert tiered.delete("k1") is True
    assert "k1" not in tiered

    tiered.set("k2", 200)
    tiered.clear()
    assert len(tiered) == 0


def test_tiered_cache_write_around():
    l1 = LRUCache(maxsize=10)
    l2 = LRUCache(maxsize=100)
    tiered = TieredCache(l1=l1, l2=l2, write_through=False)

    tiered.set("direct_to_l2", "val")
    assert "direct_to_l2" not in l1
    assert "direct_to_l2" in l2

    # First read promotes to L1
    assert tiered.get("direct_to_l2") == "val"
    assert "direct_to_l2" in l1
