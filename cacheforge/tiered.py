"""Tiered multi-layer caching combining high-speed memory (L1) with persistent disk (L2)."""

from __future__ import annotations

import threading
from typing import (
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Tuple,
    TypeVar,
)

from cacheforge.base import BaseCache

K = TypeVar("K")
V = TypeVar("V")


class TieredCache(BaseCache[K, V]):
    """Hierarchical two-tier cache combining fast L1 memory with persistent L2 storage.

    On reads:
    1. Checks L1 cache (e.g., in-memory LRUCache).
    2. If missing in L1, checks L2 cache (e.g., DiskCache).
    3. On an L2 hit, automatically promotes the value back into L1.

    On writes:
    Writes can be 'write-through' (written to both L1 and L2 immediately) or
    'write-around' (written to L2, loaded into L1 only upon subsequent read).
    """

    def __init__(
        self,
        l1: BaseCache[K, V],
        l2: BaseCache[K, V],
        write_through: bool = True,
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
        self.l1 = l1
        self.l2 = l2
        self.write_through = write_through
        self._lock = threading.RLock()

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        with self._lock:
            # 1. Attempt L1 lookup
            val = self.l1.get(key)
            if val is not None or key in self.l1:
                self.metrics.record_hit()
                if self.on_hit:
                    self.on_hit(key, val)  # type: ignore[arg-type]
                return val

            # 2. Attempt L2 lookup
            val2 = self.l2.get(key)
            if val2 is not None or key in self.l2:
                # Promote to L1
                self.l1.set(key, val2)  # type: ignore[arg-type]
                self.metrics.record_hit()
                if self.on_hit:
                    self.on_hit(key, val2)  # type: ignore[arg-type]
                return val2

            # 3. Cache Miss
            self.metrics.record_miss()
            if self.on_miss:
                self.on_miss(key)
            return default

    def set(
        self,
        key: K,
        value: V,
        ttl: Optional[float] = None,
        cost: int = 1,
    ) -> None:
        with self._lock:
            if self.write_through:
                self.l1.set(key, value, ttl=ttl, cost=cost)
                self.l2.set(key, value, ttl=ttl, cost=cost)
            else:
                # Write-around: write to L2, invalidate or skip L1
                self.l1.delete(key)
                self.l2.set(key, value, ttl=ttl, cost=cost)

            self.metrics.record_set()

    def delete(self, key: K) -> bool:
        with self._lock:
            del_l1 = self.l1.delete(key)
            del_l2 = self.l2.delete(key)
            deleted = del_l1 or del_l2
            if deleted:
                self.metrics.record_delete()
            return deleted

    def clear(self) -> None:
        with self._lock:
            self.l1.clear()
            self.l2.clear()

    def prune_expired(self) -> int:
        with self._lock:
            p1 = self.l1.prune_expired()
            p2 = self.l2.prune_expired()
            total = p1 + p2
            if total > 0:
                self.metrics.record_expiration(total)
            return total

    def __contains__(self, key: K) -> bool:
        with self._lock:
            return key in self.l1 or key in self.l2

    def __len__(self) -> int:
        with self._lock:
            return len(set(self.l1.keys()).union(set(self.l2.keys())))

    def __iter__(self) -> Iterator[K]:
        return iter(self.keys())

    def keys(self) -> List[K]:
        with self._lock:
            combined = set(self.l1.keys()).union(set(self.l2.keys()))
            return list(combined)

    def values(self) -> List[V]:
        with self._lock:
            return [self.get(k) for k in self.keys()]  # type: ignore[misc]

    def items(self) -> List[Tuple[K, V]]:
        with self._lock:
            return [(k, self.get(k)) for k in self.keys()]  # type: ignore[misc]

    def info(self) -> Dict[str, Any]:
        with self._lock:
            inf = super().info()
            inf.update(
                {
                    "write_through": self.write_through,
                    "l1": self.l1.info(),
                    "l2": self.l2.info(),
                }
            )
            return inf
