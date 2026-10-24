"""Example 1: Basic in-memory caching with LRU, TTL, and Metrics."""

from cacheforge import LRUCache, TTLCache
import time

def main():
    print("=== LRU Cache Demo ===")
    lru = LRUCache(maxsize=3)
    lru.set("user:1", {"name": "Alice"})
    lru.set("user:2", {"name": "Bob"})
    lru.set("user:3", {"name": "Charlie"})

    # Access user:1 so it becomes most recently used
    _ = lru.get("user:1")

    # Add user:4 (capacity 3 reached, evicts user:2)
    lru.set("user:4", {"name": "Diana"})

    print("Keys in LRU cache:", lru.keys())
    print("user:2 evicted?", lru.get("user:2") is None)
    print("LRU metrics:", lru.metrics)

    print("\n=== TTL Cache Demo ===")
    ttl_cache = TTLCache(default_ttl=1.0, maxsize=10)
    ttl_cache.set("session_token", "abc-123")
    print("Immediate get:", ttl_cache.get("session_token"))
    print("TTL remaining (s):", round(ttl_cache.ttl_remaining("session_token"), 2))

    print("Sleeping for 1.1 seconds...")
    time.sleep(1.1)
    print("After expiration get:", ttl_cache.get("session_token"))
    print("TTL metrics:", ttl_cache.metrics)

if __name__ == "__main__":
    main()
