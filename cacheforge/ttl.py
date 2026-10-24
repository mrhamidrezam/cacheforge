"""Time-To-Live (TTL) and Sliding TTL Cache implementations."""

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


class TTLCache(BaseCache[K, V]):
    """Thread-safe Time-To-Live (TTL) cache.

    Entries expire after a fixed duration. If maxsize is configured and capacity
    is reached, the earliest-expiring entry is evicted first.
    """

    def __init__(
        self,
        default_ttl: float,
        maxsize: Optional[int] = 1000,
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
        if default_ttl <= 0:
            raise ValueError("default_ttl must be positive")
        if maxsize is not None and maxsize < 0:
            raise ValueError("maxsize must be non-negative or None")

        self.default_ttl = default_ttl
        self.maxsize = maxsize
        self._entries: Dict[K, CacheEntry[V]] = {}
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
                self._remove_key(key, expired=True)
                self.metrics.record_miss()
                if self.on_miss:
                    self.on_miss(key)
                return default

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
        if effective_ttl <= 0:
            raise ValueError("TTL must be greater than zero")

        now = time.time()
        expires_at = now + effective_ttl

        with self._lock:
            if key in self._entries:
                entry = self._entries[key]
                entry.value = value
                entry.expires_at = expires_at
                entry.touch(now)
                entry.cost = cost
            else:
                # Evict expired first, then earliest expiring if full
                if self.maxsize is not None and len(self._entries) >= self.maxsize:
                    if self.prune_expired() == 0 and len(self._entries) >= self.maxsize:
                        self._evict_earliest_expiring()

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

    def _evict_earliest_expiring(self) -> None:
        """Evict the entry closest to expiration."""
        if not self._entries:
            return
        earliest_key = min(
            self._entries.keys(),
            key=lambda k: self._entries[k].expires_at or float("inf"),
        )
        entry = self._entries.pop(earliest_key)
        self.metrics.record_eviction()
        if self.on_evict:
            self.on_evict(earliest_key, entry.value)

    def _remove_key(self, key: K, expired: bool = False) -> Optional[CacheEntry[V]]:
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
                self._remove_key(k, expired=True)
            return len(expired_keys)

    def ttl_remaining(self, key: K) -> Optional[float]:
        """Return remaining seconds before key expires, or None if expired/not found."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry.is_expired():
                return None
            if entry.expires_at is None:
                return None
            return max(0.0, entry.expires_at - time.time())

    def __contains__(self, key: K) -> bool:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            if entry.is_expired():
                self._remove_key(key, expired=True)
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


class SlidingTTLCache(TTLCache[K, V]):
    """Thread-safe Sliding Time-To-Live Cache.

    Each successful read (`get` or access) resets the expiration timer by the item's TTL duration.
    Ideal for session state, active tokens, and sliding leases.
    """

    def __init__(
        self,
        default_ttl: float,
        maxsize: Optional[int] = 1000,
        on_hit: Optional[Callable[[K, V], None]] = None,
        on_miss: Optional[Callable[[K], None]] = None,
        on_evict: Optional[Callable[[K, V], None]] = None,
        on_expire: Optional[Callable[[K, V], None]] = None,
    ) -> None:
        super().__init__(
            default_ttl=default_ttl,
            maxsize=maxsize,
            on_hit=on_hit,
            on_miss=on_miss,
            on_evict=on_evict,
            on_expire=on_expire,
        )
        self._key_ttls: Dict[K, float] = {}

    def set(
        self,
        key: K,
        value: V,
        ttl: Optional[float] = None,
        cost: int = 1,
    ) -> None:
        effective_ttl = ttl if ttl is not None else self.default_ttl
        with self._lock:
            super().set(key, value, ttl=effective_ttl, cost=cost)
            self._key_ttls[key] = effective_ttl

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
                self._key_ttls.pop(key, None)
                self._remove_key(key, expired=True)
                self.metrics.record_miss()
                if self.on_miss:
                    self.on_miss(key)
                return default

            # Sliding extension!
            slide_ttl = self._key_ttls.get(key, self.default_ttl)
            entry.expires_at = now + slide_ttl
            entry.touch(now)

            self.metrics.record_hit()
            if self.on_hit:
                self.on_hit(key, entry.value)
            return entry.value

    def delete(self, key: K) -> bool:
        with self._lock:
            self._key_ttls.pop(key, None)
            return super().delete(key)

    def clear(self) -> None:
        with self._lock:
            self._key_ttls.clear()
            super().clear()
