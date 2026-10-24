"""Cache metrics and statistics tracking."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class CacheMetrics:
    """Thread-safe statistics tracking for cache operations."""

    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    evictions: int = 0
    expirations: int = 0

    def __post_init__(self) -> None:
        self._lock = threading.Lock()

    def record_hit(self) -> None:
        """Increment cache hit counter."""
        with self._lock:
            self.hits += 1

    def record_miss(self) -> None:
        """Increment cache miss counter."""
        with self._lock:
            self.misses += 1

    def record_set(self) -> None:
        """Increment cache set/update counter."""
        with self._lock:
            self.sets += 1

    def record_delete(self) -> None:
        """Increment cache delete counter."""
        with self._lock:
            self.deletes += 1

    def record_eviction(self, count: int = 1) -> None:
        """Increment cache eviction counter."""
        with self._lock:
            self.evictions += count

    def record_expiration(self, count: int = 1) -> None:
        """Increment expired keys pruned counter."""
        with self._lock:
            self.expirations += count

    @property
    def total_lookups(self) -> int:
        """Total number of lookups (hits + misses)."""
        with self._lock:
            return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        """Hit rate percentage between 0.0 and 1.0."""
        with self._lock:
            total = self.hits + self.misses
            if total == 0:
                return 0.0
            return self.hits / total

    @property
    def miss_rate(self) -> float:
        """Miss rate percentage between 0.0 and 1.0."""
        with self._lock:
            total = self.hits + self.misses
            if total == 0:
                return 0.0
            return self.misses / total

    def reset(self) -> None:
        """Reset all counters to zero."""
        with self._lock:
            self.hits = 0
            self.misses = 0
            self.sets = 0
            self.deletes = 0
            self.evictions = 0
            self.expirations = 0

    def to_dict(self) -> Dict[str, Any]:
        """Export metrics as a dictionary."""
        with self._lock:
            total = self.hits + self.misses
            hr = (self.hits / total) if total > 0 else 0.0
            mr = (self.misses / total) if total > 0 else 0.0
            return {
                "hits": self.hits,
                "misses": self.misses,
                "total_lookups": total,
                "hit_rate": round(hr, 4),
                "miss_rate": round(mr, 4),
                "sets": self.sets,
                "deletes": self.deletes,
                "evictions": self.evictions,
                "expirations": self.expirations,
            }

    def __repr__(self) -> str:
        d = self.to_dict()
        return (
            f"CacheMetrics(hits={d['hits']}, misses={d['misses']}, "
            f"hit_rate={d['hit_rate'] * 100:.1f}%, evictions={d['evictions']}, "
            f"expirations={d['expirations']})"
        )
