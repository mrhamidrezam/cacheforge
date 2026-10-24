"""Tests for multi-threaded concurrency safety."""

import concurrent.futures
import threading
from cacheforge.decorators import cached
from cacheforge.disk import DiskCache
from cacheforge.lru import LRUCache
from cacheforge.ttl import TTLCache


def test_concurrent_lru_reads_and_writes():
    cache = LRUCache(maxsize=100)

    def worker(worker_id: int):
        for i in range(100):
            key = f"key_{i % 20}"
            cache.set(key, f"worker_{worker_id}_val_{i}")
            _ = cache.get(key)
            if i % 10 == 0:
                cache.delete(key)

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(cache) <= 100


def test_concurrent_ttl_reads_and_writes():
    cache = TTLCache(default_ttl=10.0, maxsize=50)

    def worker(worker_id: int):
        for i in range(50):
            key = f"ttl_{i % 10}"
            cache.set(key, f"val_{i}")
            _ = cache.get(key)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(worker, i) for i in range(6)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(cache) <= 50


def test_cached_stampede_protection_multi_thread():
    computations = 0
    lock = threading.Lock()

    @cached(stampede_protect=True)
    def expensive_fetch(key_name: str) -> str:
        nonlocal computations
        with lock:
            computations += 1
        import time
        time.sleep(0.05)
        return f"result_for_{key_name}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(expensive_fetch, "stampede_key") for _ in range(10)]
        results = [f.result() for f in futures]

    assert results == ["result_for_stampede_key"] * 10
    # Even though 10 threads called simultaneously on a cold cache, expensive_fetch ran exactly once!
    assert computations == 1
