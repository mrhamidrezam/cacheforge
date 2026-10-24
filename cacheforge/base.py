"""Base cache interfaces, entries, and abstract classes."""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    Iterator,
    List,
    Optional,
    Tuple,
    TypeVar,
)

from cacheforge.metrics import CacheMetrics

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class CacheEntry(Generic[V]):
    """Internal representation of a cached item."""

    key: Any
    value: V
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    access_count: int = 1
    last_accessed: float = field(default_factory=time.time)
    cost: int = 1

    def is_expired(self, now: Optional[float] = None) -> bool:
        """Check if this entry has passed its expiration time."""
        if self.expires_at is None:
            return False
        current = now if now is not None else time.time()
        return current >= self.expires_at

    def touch(self, now: Optional[float] = None) -> None:
        """Update access timestamp and increment access counter."""
        self.last_accessed = now if now is not None else time.time()
        self.access_count += 1


class BaseCache(abc.ABC, Generic[K, V]):
    """Abstract Base Class for all Cache implementations."""

    def __init__(
        self,
        on_hit: Optional[Callable[[K, V], None]] = None,
        on_miss: Optional[Callable[[K], None]] = None,
        on_evict: Optional[Callable[[K, V], None]] = None,
        on_expire: Optional[Callable[[K, V], None]] = None,
    ) -> None:
        self.metrics = CacheMetrics()
        self.on_hit = on_hit
        self.on_miss = on_miss
        self.on_evict = on_evict
        self.on_expire = on_expire

    @abc.abstractmethod
    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """Retrieve an item from the cache. Returns default if not found or expired."""
        raise NotImplementedError

    @abc.abstractmethod
    def set(
        self,
        key: K,
        value: V,
        ttl: Optional[float] = None,
        cost: int = 1,
    ) -> None:
        """Store an item in the cache with an optional TTL in seconds."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete(self, key: K) -> bool:
        """Remove a key from the cache. Returns True if found and deleted."""
        raise NotImplementedError

    @abc.abstractmethod
    def clear(self) -> None:
        """Clear all entries from the cache."""
        raise NotImplementedError

    @abc.abstractmethod
    def __len__(self) -> int:
        """Return the number of unexpired items in the cache."""
        raise NotImplementedError

    @abc.abstractmethod
    def __contains__(self, key: K) -> bool:
        """Check if key exists in the cache and is not expired."""
        raise NotImplementedError

    def contains(self, key: K) -> bool:
        """Check if key exists and is not expired without updating access order."""
        return key in self

    def __getitem__(self, key: K) -> V:
        val = self.get(key)
        if val is None and key not in self:
            raise KeyError(key)
        return val  # type: ignore[return-value]

    def __setitem__(self, key: K, value: V) -> None:
        self.set(key, value)

    def __delitem__(self, key: K) -> None:
        if not self.delete(key):
            raise KeyError(key)

    def pop(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """Remove specified key and return the corresponding value, or default."""
        val = self.get(key)
        if val is not None or key in self:
            self.delete(key)
            return val
        return default

    def get_or_set(
        self,
        key: K,
        default_factory: Callable[[], V],
        ttl: Optional[float] = None,
        cost: int = 1,
    ) -> V:
        """Get an existing item, or compute and set it via default_factory if absent."""
        val = self.get(key)
        if val is not None or key in self:
            return val  # type: ignore[return-value]
        computed = default_factory()
        self.set(key, computed, ttl=ttl, cost=cost)
        return computed

    @abc.abstractmethod
    def prune_expired(self) -> int:
        """Manually purge all expired keys and return count of pruned entries."""
        raise NotImplementedError

    @abc.abstractmethod
    def keys(self) -> List[K]:
        """Return a list of non-expired keys currently in the cache."""
        raise NotImplementedError

    @abc.abstractmethod
    def values(self) -> List[V]:
        """Return a list of non-expired values currently in the cache."""
        raise NotImplementedError

    @abc.abstractmethod
    def items(self) -> List[Tuple[K, V]]:
        """Return a list of (key, value) pairs currently in the cache."""
        raise NotImplementedError

    def info(self) -> Dict[str, Any]:
        """Return operational summary dictionary."""
        return {
            "size": len(self),
            "metrics": self.metrics.to_dict(),
        }
