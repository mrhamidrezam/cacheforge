"""High-level caching decorators for sync and async functions."""

from __future__ import annotations

import functools
import hashlib
import inspect
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Optional,
    TypeVar,
    Union,
    cast,
)

from cacheforge.base import BaseCache
from cacheforge.lru import LRUCache
from cacheforge.singleflight import AsyncSingleFlight, SingleFlight

F = TypeVar("F", bound=Callable[..., Any])


def _default_key_builder(func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Deterministic cache key builder based on function name and serialized arguments."""
    arg_reprs = []
    for a in args:
        arg_reprs.append(repr(a))
    for k in sorted(kwargs.keys()):
        arg_reprs.append(f"{k}={repr(kwargs[k])}")

    payload = f"{func.__module__}:{func.__qualname__}({','.join(arg_reprs)})"
    if len(payload) > 128:
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"{func.__qualname__}:{digest}"
    return payload


def cached(
    cache: Optional[BaseCache[Any, Any]] = None,
    ttl: Optional[float] = None,
    key_builder: Optional[Callable[..., Any]] = None,
    unless: Optional[Callable[[Any], bool]] = None,
    stampede_protect: bool = False,
) -> Callable[[F], F]:
    """Decorator to cache results of a synchronous function.

    Args:
        cache: Cache instance to use. If None, a thread-safe LRUCache(1024) is created.
        ttl: Optional time-to-live in seconds.
        key_builder: Optional custom key generator: `key_builder(func, args, kwargs)`.
        unless: Optional predicate `unless(result) -> bool`. If True, result is not stored.
        stampede_protect: If True, uses SingleFlight to coalesce concurrent misses.
    """
    target_cache = cache if cache is not None else LRUCache(maxsize=1024)
    flight = SingleFlight[Any, Any]() if stampede_protect else None
    builder = key_builder or _default_key_builder

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_key = builder(fn, args, kwargs)

            # Check cache
            cached_val = target_cache.get(cache_key)
            if cached_val is not None or cache_key in target_cache:
                return cached_val

            # Compute value with optional stampede protection
            def _compute() -> Any:
                # Double-check inside leader block
                v = target_cache.get(cache_key)
                if v is not None or cache_key in target_cache:
                    return v
                res = fn(*args, **kwargs)
                if unless is None or not unless(res):
                    target_cache.set(cache_key, res, ttl=ttl)
                return res

            if flight is not None:
                return flight.do(cache_key, _compute)
            return _compute()

        # Attach management helpers
        def cache_clear() -> None:
            target_cache.clear()

        def cache_info() -> Dict[str, Any]:
            return target_cache.info()

        def invalidate(*args: Any, **kwargs: Any) -> bool:
            k = builder(fn, args, kwargs)
            return target_cache.delete(k)

        wrapper.cache = target_cache  # type: ignore[attr-defined]
        wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
        wrapper.cache_info = cache_info  # type: ignore[attr-defined]
        wrapper.invalidate = invalidate  # type: ignore[attr-defined]

        return cast(F, wrapper)

    return decorator


def acached(
    cache: Optional[BaseCache[Any, Any]] = None,
    ttl: Optional[float] = None,
    key_builder: Optional[Callable[..., Any]] = None,
    unless: Optional[Callable[[Any], bool]] = None,
    stampede_protect: bool = False,
) -> Callable[[F], F]:
    """Decorator to cache results of an asynchronous coroutine function.

    Args:
        cache: Cache instance to use. If None, a thread-safe LRUCache(1024) is created.
        ttl: Optional time-to-live in seconds.
        key_builder: Optional custom key generator: `key_builder(func, args, kwargs)`.
        unless: Optional predicate `unless(result) -> bool`. If True, result is not stored.
        stampede_protect: If True, uses AsyncSingleFlight to coalesce concurrent misses.
    """
    target_cache = cache if cache is not None else LRUCache(maxsize=1024)
    async_flight = AsyncSingleFlight[Any, Any]() if stampede_protect else None
    builder = key_builder or _default_key_builder

    def decorator(fn: F) -> F:
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(f"@acached can only decorate coroutine functions, got {fn}")

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_key = builder(fn, args, kwargs)

            cached_val = target_cache.get(cache_key)
            if cached_val is not None or cache_key in target_cache:
                return cached_val

            async def _compute_async() -> Any:
                v = target_cache.get(cache_key)
                if v is not None or cache_key in target_cache:
                    return v
                res = await fn(*args, **kwargs)
                if unless is None or not unless(res):
                    target_cache.set(cache_key, res, ttl=ttl)
                return res

            if async_flight is not None:
                return await async_flight.do(cache_key, _compute_async)
            return await _compute_async()

        def cache_clear() -> None:
            target_cache.clear()

        def cache_info() -> Dict[str, Any]:
            return target_cache.info()

        def invalidate(*args: Any, **kwargs: Any) -> bool:
            k = builder(fn, args, kwargs)
            return target_cache.delete(k)

        wrapper.cache = target_cache  # type: ignore[attr-defined]
        wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
        wrapper.cache_info = cache_info  # type: ignore[attr-defined]
        wrapper.invalidate = invalidate  # type: ignore[attr-defined]

        return cast(F, wrapper)

    return decorator
