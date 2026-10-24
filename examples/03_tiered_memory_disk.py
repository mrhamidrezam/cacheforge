"""Example 3: Hierarchical Tiered Cache (L1 Memory + L2 SQLite Disk)."""

import pathlib
import shutil
from cacheforge import DiskCache, LRUCache, TieredCache

def main():
    storage_dir = pathlib.Path("./.demo_tiered_cache")
    if storage_dir.exists():
        shutil.rmtree(storage_dir)

    # L1: fast RAM cache (small capacity: 2 items)
    l1 = LRUCache(maxsize=2)
    # L2: durable disk cache backed by SQLite
    l2 = DiskCache(directory=storage_dir, maxsize=1000)

    tiered = TieredCache(l1=l1, l2=l2)

    print("=== Populating Tiered Cache ===")
    tiered.set("doc:1", {"title": "Architecture Overview", "pages": 12})
    tiered.set("doc:2", {"title": "API Specification", "pages": 45})
    tiered.set("doc:3", {"title": "Security Guidelines", "pages": 8})

    print(f"L1 (Memory) Keys: {l1.keys()} (Doc 1 evicted from L1 due to maxsize=2)")
    print(f"L2 (Disk) Keys  : {l2.keys()} (All documents persisted safely on disk)")

    print("\n=== Reading doc:1 from Tiered Cache ===")
    doc1 = tiered.get("doc:1")
    print("Retrieved doc:1:", doc1)
    print(f"L1 Keys after retrieval: {l1.keys()} (Notice doc:1 was promoted back into L1 RAM!)")

    l2.close()
    if storage_dir.exists():
        shutil.rmtree(storage_dir)

if __name__ == "__main__":
    main()
