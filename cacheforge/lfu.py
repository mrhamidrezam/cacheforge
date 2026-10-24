"""Least Frequently Used (LFU) Cache implementation with O(1) operations."""

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


class LFUCache(BaseCache[K, V]):
    """Thread-safe Least Frequently Used (LFU) cache with O(1) operations.

    When evicting among keys with identical frequencies, Least Recently Used (LRU)
    order is used as the deterministic tie-breaker.
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
            raise ValueError("LFUCache maxsize must be greater than 0")
        if default_ttl is not None and default_ttl < 0:
            raise ValueError("default_ttl must be non-negative or None")

        self.maxsize = maxsize
        self.default_ttl = default_ttl
        self._entries: Dict[K, CacheEntry[V]] = {}
        self._key_to_freq: Dict[K, int] = {}
        self._freq_to_keys: Dict[int, collections.OrderedDict[K, None]] = (
            collections.defaultdict(collections.OrderedDict)
        )
        self._min_freq = 0
        self._lock = threading.RLock()

    def _increment_freq(self, key: K) -> None:
        """Promote a key to the next frequency bucket."""
        freq = self._key_to_freq[key]
        self._key_to_freq[key] = freq + 1

        # Remove from old bucket
        del self._freq_to_keys[freq][key]
        if not self._freq_to_keys[freq]:
            del self._freq_to_keys[freq]
            if self._min_freq == freq:
                self._min_freq += 1

        # Insert into new bucket
        self._freq_to_keys[freq + 1][key] = None

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

            self._increment_freq(key)
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
                self._increment_freq(key)
            else:
                # Need to evict if capacity reached
                if len(self._entries) >= self.maxsize:
                    self._evict_one()

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
                self._key_to_freq[key] = 1
                self._freq_to_keys[1][key] = None
                self._min_freq = 1

            self.metrics.record_set()

    def _evict_one(self) -> None:
        """Evict the least frequently used key (LRU tie-breaker)."""
        if not self._entries:
            return

        min_bucket = self._freq_to_keys.get(self._min_freq)
        if not min_bucket:
            # Fallback if min_freq is somehow out of sync
            if self._freq_to_keys:
                self._min_freq = min(self._freq_to_keys.keys())
                min_bucket = self._freq_to_keys[self._min_freq]
            else:
                return

        # Pop least recently used within this lowest frequency
        evicted_key, _ = min_bucket.popitem(last=False)
        entry = self._entries.pop(evicted_key, None)
        self._key_to_freq.pop(evicted_key, None)

        if not min_bucket:
            del self._freq_to_keys[self._min_freq]

        self.metrics.record_eviction()
        if self.on_evict and entry is not None:
            self.on_evict(evicted_key, entry.value)

    def _remove_key(self, key: K, expired: bool = False) -> Optional[CacheEntry[V]]:
        """Remove key from internal mappings."""
        entry = self._entries.pop(key, None)
        if entry is None:
            return None

        freq = self._key_to_freq.pop(key, None)
        if freq is not None and freq in self._freq_to_keys:
            self._freq_to_keys[freq].pop(key, None)
            if not self._freq_to_keys[freq]:
                del self._freq_to_keys[freq]

        if expired:
            self.metrics.record_expiration()
            if self.on_expire:
                self.on_expire(key, entry.value)
        return entry

    def delete(self, key: K) -> bool:
        with self._lock:
            entry = self._remove_key(key, expired=False)
            if entry is not None:
                self.metrics.record_delete()
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._key_to_freq.clear()
            self._freq_to_keys.clear()
            self._min_freq = 0

    def prune_expired(self) -> int:
        with self._lock:
            now = time.time()
            expired_keys = [
                k for k, v in self._entries.items() if v.is_expired(now)
            ]
            for k in expired_keys:
                self._remove_key(k, expired=True)
            return len(expired_keys)

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

    def frequency(self, key: K) -> Optional[int]:
        """Return the current access frequency of a key."""
        with self._lock:
            if key in self:
                return self._key_to_freq.get(key)
            return None

    def info(self) -> Dict[str, Any]:
        with self._lock:
            inf = super().info()
            inf.update(
                {
                    "maxsize": self.maxsize,
                    "default_ttl": self.default_ttl,
                    "min_freq": self._min_freq,
                }
            )
            return inf
