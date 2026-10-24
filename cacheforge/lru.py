"""Least Recently Used (LRU) Cache implementation."""

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


class LRUCache(BaseCache[K, V]):
    """Thread-safe Least Recently Used (LRU) cache with TTL and cost support."""

    def __init__(
        self,
        maxsize: Optional[int] = 1000,
        default_ttl: Optional[float] = None,
        max_cost: Optional[int] = None,
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
        if maxsize is not None and maxsize < 0:
            raise ValueError("maxsize must be non-negative or None")
        if default_ttl is not None and default_ttl < 0:
            raise ValueError("default_ttl must be non-negative or None")
        if max_cost is not None and max_cost < 0:
            raise ValueError("max_cost must be non-negative or None")

        self.maxsize = maxsize
        self.default_ttl = default_ttl
        self.max_cost = max_cost
        self._entries: collections.OrderedDict[K, CacheEntry[V]] = (
            collections.OrderedDict()
        )
        self._current_cost = 0
        self._lock = threading.RLock()

    @property
    def current_cost(self) -> int:
        """Current total cost of stored entries."""
        with self._lock:
            return self._current_cost

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
                # Expired key
                self._remove_entry(key, expired=True)
                self.metrics.record_miss()
                if self.on_miss:
                    self.on_miss(key)
                return default

            # Cache hit: move to most-recently used position
            self._entries.move_to_end(key)
            entry.touch(now)
            self.metrics.record_hit()
            if self.on_hit:
                self.on_hit(key, entry.value)
            return entry.value

    def peek(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """View value without altering LRU order or recording hit/miss."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry.is_expired():
                return default
            return entry.value

    def set(
        self,
        key: K,
        value: V,
        ttl: Optional[float] = None,
        cost: int = 1,
    ) -> None:
        if cost < 0:
            raise ValueError("cost must be non-negative")

        effective_ttl = ttl if ttl is not None else self.default_ttl
        expires_at = (time.time() + effective_ttl) if effective_ttl is not None else None

        with self._lock:
            now = time.time()
            if key in self._entries:
                old_entry = self._entries[key]
                self._current_cost -= old_entry.cost
                old_entry.value = value
                old_entry.expires_at = expires_at
                old_entry.touch(now)
                old_entry.cost = cost
                self._current_cost += cost
                self._entries.move_to_end(key)
            else:
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
                self._current_cost += cost

            self.metrics.record_set()
            self._evict_excess()

    def _remove_entry(self, key: K, expired: bool = False) -> Optional[CacheEntry[V]]:
        """Internal helper to remove entry and adjust metrics/cost."""
        entry = self._entries.pop(key, None)
        if entry is not None:
            self._current_cost -= entry.cost
            if expired:
                self.metrics.record_expiration()
                if self.on_expire:
                    self.on_expire(key, entry.value)
            return entry
        return None

    def _evict_excess(self) -> None:
        """Evict oldest entries to satisfy maxsize and max_cost."""
        # Evict until size constraint met
        if self.maxsize is not None and self.maxsize > 0:
            while len(self._entries) > self.maxsize:
                evicted_key, evicted_entry = self._entries.popitem(last=False)
                self._current_cost -= evicted_entry.cost
                self.metrics.record_eviction()
                if self.on_evict:
                    self.on_evict(evicted_key, evicted_entry.value)

        # Evict until cost constraint met
        if self.max_cost is not None:
            while self._current_cost > self.max_cost and self._entries:
                evicted_key, evicted_entry = self._entries.popitem(last=False)
                self._current_cost -= evicted_entry.cost
                self.metrics.record_eviction()
                if self.on_evict:
                    self.on_evict(evicted_key, evicted_entry.value)

    def delete(self, key: K) -> bool:
        with self._lock:
            entry = self._entries.pop(key, None)
            if entry is not None:
                self._current_cost -= entry.cost
                self.metrics.record_delete()
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._current_cost = 0

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
                    "current_cost": self._current_cost,
                    "max_cost": self.max_cost,
                }
            )
            return inf
