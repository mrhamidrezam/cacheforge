"""Persistent disk-backed cache using standard library SQLite."""

from __future__ import annotations

import os
import pathlib
import sqlite3
import threading
import time
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

from cacheforge.base import BaseCache
from cacheforge.serializers import BaseSerializer, CompressedSerializer, PickleSerializer

K = TypeVar("K")
V = TypeVar("V")


class DiskCache(BaseCache[K, V]):
    """Thread-safe persistent disk cache powered by SQLite in Write-Ahead Log (WAL) mode.

    Provides durable storage across process restarts, automatic LRU eviction when
    maxsize is exceeded, TTL support, and zero external dependencies.
    """

    def __init__(
        self,
        directory: Union[str, pathlib.Path] = ".cacheforge_data",
        filename: str = "cache.db",
        maxsize: Optional[int] = 10000,
        default_ttl: Optional[float] = None,
        serializer: Optional[BaseSerializer] = None,
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
        self.dir_path = pathlib.Path(directory)
        self.dir_path.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir_path / filename

        self.maxsize = maxsize
        self.default_ttl = default_ttl
        self.serializer = serializer or CompressedSerializer(PickleSerializer())

        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=30.0,
            isolation_level=None,  # Autocommit mode
        )
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema, pragmas, and indexes."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("PRAGMA journal_mode = WAL;")
            cur.execute("PRAGMA synchronous = NORMAL;")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value BLOB NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL,
                    access_count INTEGER NOT NULL DEFAULT 1,
                    last_accessed REAL NOT NULL,
                    cost INTEGER NOT NULL DEFAULT 1
                );
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_accessed ON cache(last_accessed);"
            )
            cur.close()

    def _key_to_str(self, key: Any) -> str:
        """Convert arbitrary key to string representation for SQL storage."""
        if isinstance(key, str):
            return key
        return repr(key)

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        skey = self._key_to_str(key)
        now = time.time()

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?;",
                (skey,),
            )
            row = cur.fetchone()

            if row is None:
                cur.close()
                self.metrics.record_miss()
                if self.on_miss:
                    self.on_miss(key)
                return default

            raw_val, expires_at = row
            if expires_at is not None and now >= expires_at:
                # Key is expired
                cur.execute("DELETE FROM cache WHERE key = ?;", (skey,))
                cur.close()
                self.metrics.record_expiration()
                self.metrics.record_miss()
                if self.on_expire:
                    self.on_expire(key, default)  # type: ignore[arg-type]
                if self.on_miss:
                    self.on_miss(key)
                return default

            # Cache hit: touch last_accessed and increment access_count
            cur.execute(
                """
                UPDATE cache
                SET last_accessed = ?, access_count = access_count + 1
                WHERE key = ?;
                """,
                (now, skey),
            )
            cur.close()

            val = self.serializer.deserialize(raw_val)
            self.metrics.record_hit()
            if self.on_hit:
                self.on_hit(key, val)
            return val

    def set(
        self,
        key: K,
        value: V,
        ttl: Optional[float] = None,
        cost: int = 1,
    ) -> None:
        skey = self._key_to_str(key)
        effective_ttl = ttl if ttl is not None else self.default_ttl
        now = time.time()
        expires_at = (now + effective_ttl) if effective_ttl is not None else None
        serialized = self.serializer.serialize(value)

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO cache (key, value, created_at, expires_at, access_count, last_accessed, cost)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    expires_at = excluded.expires_at,
                    access_count = cache.access_count + 1,
                    last_accessed = excluded.last_accessed,
                    cost = excluded.cost;
                """,
                (skey, serialized, now, expires_at, now, cost),
            )
            cur.close()
            self.metrics.record_set()
            self._evict_excess()

    def _evict_excess(self) -> None:
        """Evict oldest entries when maxsize is exceeded."""
        if self.maxsize is None or self.maxsize <= 0:
            return

        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT COUNT(*) FROM cache;")
            count = cur.fetchone()[0]

            if count > self.maxsize:
                excess = count - self.maxsize
                cur.execute(
                    """
                    SELECT key, value FROM cache
                    ORDER BY last_accessed ASC
                    LIMIT ?;
                    """,
                    (excess,),
                )
                evicted_rows = cur.fetchall()

                cur.execute(
                    """
                    DELETE FROM cache WHERE key IN (
                        SELECT key FROM cache ORDER BY last_accessed ASC LIMIT ?
                    );
                    """,
                    (excess,),
                )
                self.metrics.record_eviction(len(evicted_rows))

                if self.on_evict:
                    for ev_key, ev_val in evicted_rows:
                        try:
                            deserialized = self.serializer.deserialize(ev_val)
                        except Exception:
                            deserialized = None
                        self.on_evict(ev_key, deserialized)  # type: ignore[arg-type]
            cur.close()

    def delete(self, key: K) -> bool:
        skey = self._key_to_str(key)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM cache WHERE key = ?;", (skey,))
            deleted = cur.rowcount > 0
            cur.close()
            if deleted:
                self.metrics.record_delete()
            return deleted

    def clear(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM cache;")
            cur.close()

    def prune_expired(self) -> int:
        now = time.time()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "DELETE FROM cache WHERE expires_at IS NOT NULL AND expires_at <= ?;",
                (now,),
            )
            pruned = cur.rowcount
            cur.close()
            if pruned > 0:
                self.metrics.record_expiration(pruned)
            return pruned

    def vacuum(self) -> None:
        """Reclaim unused database disk space."""
        with self._lock:
            self._conn.execute("VACUUM;")

    def size_bytes(self) -> int:
        """Return total size of database files on disk in bytes."""
        total = 0
        if self.db_path.exists():
            total += self.db_path.stat().st_size
        wal = self.dir_path / f"{self.db_path.name}-wal"
        if wal.exists():
            total += wal.stat().st_size
        shm = self.dir_path / f"{self.db_path.name}-shm"
        if shm.exists():
            total += shm.stat().st_size
        return total

    def __contains__(self, key: K) -> bool:
        skey = self._key_to_str(key)
        now = time.time()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT expires_at FROM cache WHERE key = ?;",
                (skey,),
            )
            row = cur.fetchone()
            cur.close()
            if row is None:
                return False
            expires_at = row[0]
            if expires_at is not None and now >= expires_at:
                self.delete(key)
                return False
            return True

    def __len__(self) -> int:
        self.prune_expired()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT COUNT(*) FROM cache;")
            count = cur.fetchone()[0]
            cur.close()
            return count

    def __iter__(self) -> Iterator[K]:
        return iter(self.keys())

    def keys(self) -> List[K]:
        self.prune_expired()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT key FROM cache;")
            rows = [r[0] for r in cur.fetchall()]
            cur.close()
            return rows  # type: ignore[return-value]

    def values(self) -> List[V]:
        self.prune_expired()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT value FROM cache;")
            rows = [self.serializer.deserialize(r[0]) for r in cur.fetchall()]
            cur.close()
            return rows

    def items(self) -> List[Tuple[K, V]]:
        self.prune_expired()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT key, value FROM cache;")
            rows = [
                (r[0], self.serializer.deserialize(r[1]))
                for r in cur.fetchall()
            ]
            cur.close()
            return rows  # type: ignore[return-value]

    def close(self) -> None:
        """Close SQLite database connection cleanly."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    def __enter__(self) -> DiskCache[K, V]:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def info(self) -> Dict[str, Any]:
        with self._lock:
            inf = super().info()
            inf.update(
                {
                    "path": str(self.db_path),
                    "size_bytes": self.size_bytes(),
                    "maxsize": self.maxsize,
                    "default_ttl": self.default_ttl,
                }
            )
            return inf
