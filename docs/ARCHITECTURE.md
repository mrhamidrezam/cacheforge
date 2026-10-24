# CacheForge Architecture & Internal Design

`cacheforge` is a high-performance, zero-dependency caching, tiered storage, and cache stampede protection toolkit designed for Python 3.9 through 3.14+.

---

## 1. Architectural Overview

```
                                  +------------------------+
                                  |     Application        |
                                  | (Sync / Async Caller)  |
                                  +-----------+------------+
                                              |
                          +-------------------v-------------------+
                          |     High-Level Decorator Layer        |
                          |      @cached / @acached               |
                          +-------------------+-------------------+
                                              |
                          +-------------------v-------------------+
                          |      SingleFlight Coalescer           |
                          | (Stampede / Thundering Herd Guard)    |
                          +-------------------+-------------------+
                                              |
                   +--------------------------+--------------------------+
                   |                                                     |
         +---------v---------+                                 +---------v---------+
         | In-Memory Caches  |                                 | Hierarchical Tier |
         | LRU / LFU / FIFO  |                                 |    TieredCache    |
         | TTL / Sliding TTL |                                 +---------+---------+
         +---------+---------+                                           |
                   |                                           +---------+---------+
                   |                                           |                   |
                   |                                    +------v------+     +------v------+
                   |                                    |  L1 Memory  |     |  L2 Disk    |
                   |                                    | (LRUCache)  |     | (SQLite WAL)|
                   |                                    +-------------+     +------+------+
                   |                                                               |
                   +--------------------------+------------------------------------+
                                              |
                                   +----------v----------+
                                   | Serialization &     |
                                   | zlib Compression    |
                                   +----------+----------+
                                              |
                                   +----------v----------+
                                   | Metrics & Telemetry |
                                   | (Hits, Misses, Rate)|
                                   +---------------------+
```

---

## 2. Core Design Principles

1. **Zero External Dependencies**:
   Constructed exclusively using Python's standard library (`collections`, `threading`, `sqlite3`, `zlib`, `pickle`, `json`, `asyncio`). Zero supply-chain attack surface, instant installation, minimal footprint.

2. **Strict Thread Safety**:
   Every in-memory cache implementation relies on reentrant locks (`threading.RLock`) to ensure consistent state across multi-threaded workers without data races.

3. **Stampede Resilience (Thundering Herd Protection)**:
   Concurrent cache misses on an identical key coalesce onto a single execution leader using `SingleFlight` or `AsyncSingleFlight`, preventing database brownouts during cache invalidation events.

4. **Hierarchical Composability**:
   Different storage backends can be composed seamlessly via `TieredCache`, automatically handling cache promotion (L2 hit promoted to L1) and configurable write strategies (`write-through` vs. `write-around`).

---

## 3. Cache Eviction Algorithms & Complexity

| Algorithm | Data Structure | Lookup | Insertion | Eviction Order | Tie-Breaker |
|:---|:---|:---:|:---:|:---|:---|
| **`LRUCache`** | `OrderedDict[K, CacheEntry]` | $O(1)$ | $O(1)$ | Least Recently Used | Recency of access |
| **`LFUCache`** | Bucket Hash Map `Dict[int, OrderedDict]` | $O(1)$ | $O(1)$ | Least Frequently Used | LRU within frequency bucket |
| **`FIFOCache`** | Strict `OrderedDict` FIFO queue | $O(1)$ | $O(1)$ | First-In, First-Out | Strict chronological insertion |
| **`TTLCache`** | Hash Map with expiration index | $O(1)$ | $O(1)$ | Expiration time | Earliest expiring |
| **`SlidingTTLCache`**| Hash Map with dynamic slide on `get` | $O(1)$ | $O(1)$ | Inactivity lease expiration | Dynamic touch |
| **`DiskCache`** | Persistent SQLite in WAL mode | $O(1)^*$ | $O(1)^*$ | Indexed LRU (`last_accessed`) | B-tree index traversal |

*\* SQLite indexed point lookups are $O(\log N)$ on disk B-trees, with OS page cache accelerating hot pages to near-memory speeds.*

---

## 4. SingleFlight: Cache Stampede Prevention

In traditional caching systems, when an expensively calculated or heavily requested key expires under high load, hundreds of simultaneous worker threads or coroutines miss the cache simultaneously and bombard the backend database. This phenomenon is known as the **Cache Stampede** or **Thundering Herd**.

```
Without SingleFlight:
Thread 1 (Miss) ──> [ Heavy DB Query ] ──> Store Cache
Thread 2 (Miss) ──> [ Heavy DB Query ] ──> Store Cache  (Redundant!)
Thread 3 (Miss) ──> [ Heavy DB Query ] ──> Store Cache  (Redundant!)
Thread 4 (Miss) ──> [ Heavy DB Query ] ──> Store Cache  (Redundant!)

With SingleFlight:
Thread 1 (Miss - Leader) ──> [ Heavy DB Query ] ──> Broadcast Result
Thread 2 (Miss - Waiter) ─── Wait on Event ───────> Receives Leader Result
Thread 3 (Miss - Waiter) ─── Wait on Event ───────> Receives Leader Result
Thread 4 (Miss - Waiter) ─── Wait on Event ───────> Receives Leader Result
```

`cacheforge.SingleFlight` and `cacheforge.AsyncSingleFlight` guarantee that exactly **one** computation is in flight per key. All concurrent callers await the leader's completion and receive the identical computed value or exception.

---

## 5. Persistent Storage & WAL Mode

`DiskCache` utilizes standard library `sqlite3` configured with:
- `PRAGMA journal_mode = WAL;` (Write-Ahead Logging allows simultaneous concurrent readers while a write is occurring).
- `PRAGMA synchronous = NORMAL;` (Safe ACID durability with high IOPS).
- Automatic indexing on `expires_at` and `last_accessed` for instantaneous eviction and pruning.
- Pluggable serialization layer: `PickleSerializer`, `JSONSerializer`, or `CompressedSerializer` with automatic `zlib` compression.

---

## 6. Observability and Metrics

Every cache instance maintains a thread-safe `CacheMetrics` collector tracking:
- `hits` and `misses`
- `hit_rate` ($hits / (hits + misses)$) and `miss_rate`
- `evictions` (capacity or cost bound reached)
- `expirations` (TTL expired)
- Lifecycle callbacks: `on_hit`, `on_miss`, `on_evict`, `on_expire`.
