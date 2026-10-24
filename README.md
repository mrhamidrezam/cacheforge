# CacheForge

[![CI](https://github.com/mrhamidrezam/cacheforge/actions/workflows/ci.yml/badge.svg)](https://github.com/mrhamidrezam/cacheforge/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/cacheforge.svg)](https://pypi.org/project/cacheforge/)
[![Python Version](https://img.shields.io/pypi/pyversions/cacheforge.svg)](https://pypi.org/project/cacheforge/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**CacheForge** is a high-performance, **zero-dependency** caching, tiered storage, and cache stampede protection toolkit for Python. Built strictly with standard library primitives, it combines multi-strategy in-memory algorithms (`LRU`, `LFU`, `FIFO`, `TTL`, `Sliding TTL`), persistent disk caching backed by SQLite WAL mode, and request coalescing (`SingleFlight`) to prevent thundering herd failures.

---

## Key Features

- **Zero External Dependencies**: Pure Python standard library. No native compilation hurdles, zero bloated dependency trees.
- **Multiple Eviction Policies**:
  - `LRUCache`: Least Recently Used eviction with capacity, max-cost, and TTL bounds.
  - `LFUCache`: $O(1)$ Least Frequently Used eviction with deterministic LRU tie-breaking.
  - `FIFOCache`: Strictly chronological First-In, First-Out queue eviction.
  - `TTLCache`: Time-To-Live expiration with active/passive pruning.
  - `SlidingTTLCache`: Sliding inactivity window (resets expiration on read).
- **Persistent Disk Caching (`DiskCache`)**: Durable SQLite storage in Write-Ahead Log (WAL) mode supporting multi-process concurrency, automatic pruning, and size management.
- **Tiered Multi-Layer Storage (`TieredCache`)**: Combine ultra-fast L1 memory with persistent L2 disk; automatic L2 hit promotion into L1.
- **Cache Stampede Protection (`SingleFlight` / `AsyncSingleFlight`)**: Coalesces concurrent calls on missing/expired keys, ensuring only a single loader runs while waiting threads/coroutines share the result.
- **Sync & Async Decorators**: `@cached` and `@acached` with fine-grained key builders, cache invalidation hooks (`func.invalidate(...)`), and `unless` bypass conditions.
- **Payload Serialization & Compression**: Built-in support for `PickleSerializer`, `JSONSerializer`, and `CompressedSerializer` (transparent `zlib` compression for large payloads).
- **Built-in CLI**: Benchmarking suite (`cacheforge benchmark`), disk store inspection (`cacheforge inspect`), and pruning tools (`cacheforge prune`).
- **Comprehensive Observability**: Thread-safe telemetry tracking hits, misses, hit rates, evictions, and expirations.

---

## Installation

```bash
pip install cacheforge
```

Or install in editable mode for development:

```bash
git clone https://github.com/mrhamidrezam/cacheforge.git
cd cacheforge
pip install -e .
```

---

## Quick Start

### 1. In-Memory LRU & TTL Caching

```python
from cacheforge import LRUCache, TTLCache

# In-memory LRU with capacity limit
cache = LRUCache(maxsize=1000, default_ttl=300.0)
cache.set("user:101", {"name": "Alice", "role": "admin"})

# Dict-like access
print(cache.get("user:101"))
print("user:101" in cache)

# TTL expiration
ttl_cache = TTLCache(default_ttl=60.0, maxsize=500)
ttl_cache.set("session_token", "secret_token_123")
print("Remaining TTL (seconds):", ttl_cache.ttl_remaining("session_token"))
```

### 2. Cache Stampede Prevention with SingleFlight

Protect your database from thundering herd spikes when an expensive or popular key expires:

```python
import asyncio
from cacheforge import acached

@acached(stampede_protect=True, ttl=60.0)
async def fetch_expensive_market_rates(symbol: str) -> dict:
    print(f"Executing database query for {symbol}...")
    await asyncio.sleep(0.5)
    return {"symbol": symbol, "rate": 104.25}

# If 50 coroutines invoke fetch_expensive_market_rates('EUR/USD') simultaneously,
# only 1 query executes. All 50 awaiters receive the shared result!
```

### 3. Hierarchical Tiered Caching (Memory L1 + Disk L2)

```python
from cacheforge import LRUCache, DiskCache, TieredCache

# Fast L1 in-memory RAM cache (1,000 items)
l1 = LRUCache(maxsize=1000)

# Durable L2 disk cache (100,000 items)
l2 = DiskCache(directory="./data/cache", maxsize=100000)

# Automatic fallback and promotion:
# Checks L1 -> Miss -> Checks L2 -> Hit -> Promotes to L1!
tiered = TieredCache(l1=l1, l2=l2, write_through=True)

tiered.set("report:2026-Q3", {"revenue": 5200000})
report = tiered.get("report:2026-Q3")
```

### 4. Function Decorators & Programmatic Invalidation

```python
from cacheforge import cached

@cached(ttl=600)
def compute_user_stats(user_id: int):
    # Heavy analytical computation
    return {"user_id": user_id, "score": 98.4}

# First call: computes and stores
stats = compute_user_stats(42)

# Second call: instantaneous cache hit
stats = compute_user_stats(42)

# Explicitly invalidate specific key
compute_user_stats.invalidate(42)

# Inspect metrics
print(compute_user_stats.cache_info())
```

---

## Command Line Interface (CLI)

CacheForge ships with an intuitive CLI tool:

### Run Algorithm Benchmark
```bash
cacheforge benchmark --iterations 100000 --cache-size 1000
```
Output:
```text
=================================================================
 CacheForge Benchmark: 100,000 ops | Capacity: 1,000
=================================================================
Algorithm      | Time (s)   | Ops / Sec      | Hit Rate   | Hits       | Evictions 
---------------------------------------------------------------------------
LRUCache       | 0.082      | 1,219,512      | 78.4%      | 78,400     | 20,600    
LFUCache       | 0.091      | 1,098,901      | 81.2%      | 81,200     | 17,800    
FIFOCache      | 0.075      | 1,333,333      | 72.1%      | 72,100     | 26,900    
TTLCache       | 0.088      | 1,136,363      | 78.4%      | 78,400     | 20,600    
=================================================================
```

### Inspect Disk Cache SQLite Database
```bash
cacheforge inspect ./data/cache
```

### Prune Expired Keys & Vacuum Database
```bash
cacheforge prune ./data/cache
```

---

## Architecture

For an in-depth exploration of CacheForge's internal design, lock synchronization models, and complexity analysis, see the [Architecture Guide](docs/ARCHITECTURE.md).

For development environment setup and instructions on building distribution packages, see the [Setup Guide](docs/SETUP.md).

---

## Running Tests

CacheForge is rigorously tested with over 50+ unit and concurrency tests:

```bash
pytest -v
```

---

## License

This project is licensed under the terms of the [MIT License](LICENSE).
