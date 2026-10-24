"""Command Line Interface for CacheForge tools, inspection, and benchmarks."""

from __future__ import annotations

import argparse
import os
import pathlib
import random
import sys
import time
from typing import List, Optional

from cacheforge import __version__
from cacheforge.disk import DiskCache
from cacheforge.fifo import FIFOCache
from cacheforge.lfu import LFUCache
from cacheforge.lru import LRUCache
from cacheforge.ttl import TTLCache


def run_benchmark(iterations: int = 50000, cache_size: int = 1000) -> None:
    """Run an empirical performance and hit-rate comparison across cache algorithms."""
    print("=================================================================")
    print(f" CacheForge Benchmark: {iterations:,} ops | Capacity: {cache_size:,}")
    print("=================================================================")

    # Generate synthetic workload with Zipfian skew (80/20 rule)
    rng = random.Random(42)
    keys_pool = [f"key_{int(rng.expovariate(0.005)) % (cache_size * 4)}" for _ in range(iterations)]

    caches = {
        "LRUCache": LRUCache(maxsize=cache_size),
        "LFUCache": LFUCache(maxsize=cache_size),
        "FIFOCache": FIFOCache(maxsize=cache_size),
        "TTLCache": TTLCache(default_ttl=3600.0, maxsize=cache_size),
    }

    results = []

    for name, c in caches.items():
        t0 = time.perf_counter()
        for k in keys_pool:
            val = c.get(k)
            if val is None:
                c.set(k, f"val_{k}")
        elapsed = time.perf_counter() - t0
        ops_sec = iterations / elapsed if elapsed > 0 else 0
        hit_rate = c.metrics.hit_rate * 100
        results.append((name, elapsed, ops_sec, hit_rate, c.metrics.hits, c.metrics.evictions))

    print(f"{'Algorithm':<14} | {'Time (s)':<10} | {'Ops / Sec':<14} | {'Hit Rate':<10} | {'Hits':<10} | {'Evictions':<10}")
    print("-" * 75)
    for name, elapsed, ops, hr, hits, evictions in results:
        print(f"{name:<14} | {elapsed:<10.3f} | {int(ops):<14,d} | {hr:<9.1f}% | {hits:<10,d} | {evictions:<10,d}")
    print("=================================================================")


def inspect_disk_cache(db_path_str: str) -> None:
    """Inspect the metadata and entries of a DiskCache SQLite store."""
    p = pathlib.Path(db_path_str)
    if not p.exists():
        print(f"Error: Path '{db_path_str}' does not exist.", file=sys.stderr)
        sys.exit(1)

    target_dir = p.parent if p.is_file() else p
    target_name = p.name if p.is_file() else "cache.db"

    cache = DiskCache(directory=target_dir, filename=target_name)
    inf = cache.info()
    pruned = cache.prune_expired()
    size_kb = cache.size_bytes() / 1024.0

    print("==================================================")
    print(f" CacheForge Disk Storage: {p.resolve()}")
    print("==================================================")
    print(f"  Total Valid Entries : {len(cache):,}")
    print(f"  Storage Size on Disk: {size_kb:.2f} KB ({cache.size_bytes():,} bytes)")
    print(f"  Expired Keys Purged : {pruned:,}")
    print(f"  Total Hits Recorded : {cache.metrics.hits:,}")
    print(f"  Total Misses        : {cache.metrics.misses:,}")
    print(f"  Total Evictions     : {cache.metrics.evictions:,}")
    print("==================================================")
    cache.close()


def prune_disk_cache(db_path_str: str) -> None:
    """Prune expired entries and vacuum the DiskCache SQLite store."""
    p = pathlib.Path(db_path_str)
    if not p.exists():
        print(f"Error: Path '{db_path_str}' does not exist.", file=sys.stderr)
        sys.exit(1)

    target_dir = p.parent if p.is_file() else p
    target_name = p.name if p.is_file() else "cache.db"

    cache = DiskCache(directory=target_dir, filename=target_name)
    before_size = cache.size_bytes()
    pruned = cache.prune_expired()
    cache.vacuum()
    after_size = cache.size_bytes()

    print(f"Pruned {pruned:,} expired entries.")
    print(f"Database size: {before_size:,} bytes -> {after_size:,} bytes reclaimed.")
    cache.close()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cacheforge",
        description="High-performance, zero-dependency caching toolkit for Python.",
    )
    parser.add_argument(
        "--version", "-v", action="version", version=f"cacheforge {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command")

    # Benchmark command
    bench_parser = subparsers.add_parser(
        "benchmark", help="Run comparative benchmark on cache algorithms"
    )
    bench_parser.add_argument(
        "--iterations", "-n", type=int, default=50000, help="Number of get/set operations (default: 50,000)"
    )
    bench_parser.add_argument(
        "--cache-size", "-c", type=int, default=1000, help="Maximum capacity of each cache (default: 1,000)"
    )

    # Inspect command
    inspect_parser = subparsers.add_parser(
        "inspect", help="Inspect a persistent DiskCache SQLite file"
    )
    inspect_parser.add_argument(
        "path", type=str, help="Path to DiskCache database file or directory"
    )

    # Prune command
    prune_parser = subparsers.add_parser(
        "prune", help="Purge expired entries and vacuum a DiskCache database"
    )
    prune_parser.add_argument(
        "path", type=str, help="Path to DiskCache database file or directory"
    )

    args = parser.parse_args(argv)

    if args.command == "benchmark":
        run_benchmark(iterations=args.iterations, cache_size=args.cache_size)
    elif args.command == "inspect":
        inspect_disk_cache(args.path)
    elif args.command == "prune":
        prune_disk_cache(args.path)
    else:
        parser.print_help()
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
