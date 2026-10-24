"""First-In, First-Out (FIFO) Cache implementation."""

from __future__ import annotations

import collections
import threading
import time
from typing import (
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Tuple,
    TypeVar,
)

from cacheforge.base import BaseCache, CacheEntry

K = TypeVar("K")
V = TypeVar("V")


class FIFOCache(BaseCache[K, V]):
    """Thread-safe First-In, First-Out (FIFO) cache with TTL and capacity bounds.

    Entries are evicted in strictly chronological insertion order. Reads (`get`)
    do not alter eviction priority.
    """

    def __init__(
        self,
        maxsize: int = 1000,
        default_ttl: Optional[float] = None,
        on_hit: Optional[Callable[[K, V], None]] = None,
        on_miss: Optional[Callable[[K], None]] = None,
        on_evict: Optional[Callable[[K, V], None]] = None,
        on_expire: Optional[Callable[[K, V], None]] = None,
    ) -> None:
        super().__init__(
            on_hit=on_hit,
            on_miss=on_miss,
            on_evict=on_evict,
            on_expire=on_expire,
        )
        if maxsize <= 0:
            raise ValueError("FIFOCache maxsize must be greater than 0")
        if default_ttl is not None and default_ttl < 0:
            raise ValueError("default_ttl must be non-negative or None")

        self.maxsize = maxsize
        self.default_ttl = default_ttl
        self._entries: collections.OrderedDict[K, CacheEntry[V]] = (
            collections.OrderedDict()
        )
        self._lock = threading.RLock()

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        with self._lock:
            entry = self._entries.get(key)
            now = time.time()

            if entry is None:
                self.metrics.record_miss()
                if self.on_miss:
                    self.on_miss(key)
                return default

            if entry.is_expired(now):
                self._remove_entry(key, expired=True)
                self.metrics.record_miss()
                if self.on_miss:
                    self.on_miss(key)
                return default

            # Notice: unlike LRU, we do NOT move_to_end!
            entry.touch(now)
            self.metrics.record_hit()
            if self.on_hit:
                self.on_hit(key, entry.value)
            return entry.value

    def set(
        self,
        key: K,
        value: V,
        ttl: Optional[float] = None,
        cost: int = 1,
    ) -> None:
        effective_ttl = ttl if ttl is not None else self.default_ttl
        expires_at = (time.time() + effective_ttl) if effective_ttl is not None else None

        with self._lock:
            now = time.time()
            if key in self._entries:
                entry = self._entries[key]
                entry.value = value
                entry.expires_at = expires_at
                entry.touch(now)
                entry.cost = cost
                # Existing key keeps its original insertion order!
            else:
                if len(self._entries) >= self.maxsize:
                    # Evict the oldest inserted key
                    evicted_key, evicted_entry = self._entries.popitem(last=False)
                    self.metrics.record_eviction()
                    if self.on_evict:
                        self.on_evict(evicted_key, evicted_entry.value)

                entry = CacheEntry(
                    key=key,
                    value=value,
                    created_at=now,
                    expires_at=expires_at,
                    access_count=1,
                    last_accessed=now,
                    cost=cost,
                )
                self._entries[key] = entry

            self.metrics.record_set()

    def _remove_entry(self, key: K, expired: bool = False) -> Optional[CacheEntry[V]]:
        entry = self._entries.pop(key, None)
        if entry is not None and expired:
            self.metrics.record_expiration()
            if self.on_expire:
                self.on_expire(key, entry.value)
        return entry

    def delete(self, key: K) -> bool:
        with self._lock:
            entry = self._entries.pop(key, None)
            if entry is not None:
                self.metrics.record_delete()
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def prune_expired(self) -> int:
        with self._lock:
            now = time.time()
            expired_keys = [
                k for k, v in self._entries.items() if v.is_expired(now)
            ]
            for k in expired_keys:
                self._remove_entry(k, expired=True)
            return len(expired_keys)

    def __contains__(self, key: K) -> bool:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            if entry.is_expired():
                self._remove_entry(key, expired=True)
                return False
            return True

    def __len__(self) -> int:
        with self._lock:
            self.prune_expired()
            return len(self._entries)

    def __iter__(self) -> Iterator[K]:
        with self._lock:
            self.prune_expired()
            return iter(list(self._entries.keys()))

    def keys(self) -> List[K]:
        with self._lock:
            self.prune_expired()
            return list(self._entries.keys())

    def values(self) -> List[V]:
        with self._lock:
            self.prune_expired()
            return [e.value for e in self._entries.values()]

    def items(self) -> List[Tuple[K, V]]:
        with self._lock:
            self.prune_expired()
            return [(e.key, e.value) for e in self._entries.values()]

    def info(self) -> Dict[str, Any]:
        with self._lock:
            inf = super().info()
            inf.update(
                {
                    "maxsize": self.maxsize,
                    "default_ttl": self.default_ttl,
                }
            )
            return inf
