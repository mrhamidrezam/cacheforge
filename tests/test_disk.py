"""Tests for persistent DiskCache."""

import time
from cacheforge.disk import DiskCache
from cacheforge.serializers import JSONSerializer


def test_disk_cache_basic_ops(tmp_path):
    with DiskCache(directory=tmp_path) as cache:
        cache.set("k1", {"name": "alice"})
        cache.set("k2", [1, 2, 3])

        assert cache.get("k1") == {"name": "alice"}
        assert cache.get("k2") == [1, 2, 3]
        assert cache.get("missing", 99) == 99
        assert "k1" in cache
        assert "missing" not in cache
        assert len(cache) == 2


def test_disk_cache_persistence(tmp_path):
    # Write in one instance
    cache1 = DiskCache(directory=tmp_path)
    cache1.set("persist_key", "saved_value")
    cache1.close()

    # Read back in a new separate instance
    cache2 = DiskCache(directory=tmp_path)
    assert cache2.get("persist_key") == "saved_value"
    cache2.close()


def test_disk_cache_ttl_and_prune(tmp_path):
    with DiskCache(directory=tmp_path, default_ttl=0.06) as cache:
        cache.set("temp", "fast")
        assert cache.get("temp") == "fast"

        time.sleep(0.08)
        assert cache.get("temp") is None
        assert "temp" not in cache
        assert len(cache) == 0


def test_disk_cache_eviction_lru(tmp_path):
    with DiskCache(directory=tmp_path, maxsize=2) as cache:
        cache.set("a", 1)
        cache.set("b", 2)

        # Access 'a' to make 'b' the LRU
        cache.get("a")

        # Insert 'c', should evict 'b'
        cache.set("c", 3)

        assert cache.get("b") is None
        assert cache.get("a") == 1
        assert cache.get("c") == 3
        assert len(cache) == 2


def test_disk_cache_vacuum_and_size(tmp_path):
    with DiskCache(directory=tmp_path) as cache:
        cache.set("data", "x" * 1000)
        cache.vacuum()
        assert cache.size_bytes() > 0


def test_disk_cache_delete_clear_items(tmp_path):
    with DiskCache(directory=tmp_path, serializer=JSONSerializer()) as cache:
        cache.set("k1", 10)
        cache.set("k2", 20)

        assert cache.delete("k1") is True
        assert cache.delete("k1") is False

        assert sorted(cache.keys()) == ["k2"]
        assert cache.values() == [20]
        assert cache.items() == [("k2", 20)]

        cache.clear()
        assert len(cache) == 0
