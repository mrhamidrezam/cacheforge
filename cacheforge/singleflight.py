"""Singleflight pattern for coalescing duplicate in-flight requests and preventing cache stampedes."""

from __future__ import annotations

import asyncio
import threading
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Generic,
    Optional,
    TypeVar,
)

K = TypeVar("K")
V = TypeVar("V")


class _FlightCall(Generic[V]):
    """State of an in-flight synchronous call."""

    def __init__(self) -> None:
        self.event = threading.Event()
        self.val: Optional[V] = None
        self.err: Optional[BaseException] = None
        self.done: bool = False


class SingleFlight(Generic[K, V]):
    """Thread-safe request coalescing mechanism (Cache Stampede / Thundering Herd shield).

    Ensures that for any given key, only one execution of an expensive operation is
    in-flight concurrently. All other threads waiting on the same key share the identical
    result or exception without duplicate computation.
    """

    def __init__(self) -> None:
        self._calls: Dict[K, _FlightCall[V]] = {}
        self._lock = threading.Lock()

    def do(self, key: K, fn: Callable[[], V]) -> V:
        """Execute fn if not already running for key, otherwise await existing result."""
        with self._lock:
            if key in self._calls:
                call = self._calls[key]
                leader = False
            else:
                call = _FlightCall[V]()
                self._calls[key] = call
                leader = True

        if not leader:
            call.event.wait()
            if call.err is not None:
                raise call.err
            return call.val  # type: ignore[return-value]

        # Leader executes the actual work
        try:
            val = fn()
            call.val = val
            return val
        except BaseException as err:
            call.err = err
            raise
        finally:
            with self._lock:
                call.done = True
                self._calls.pop(key, None)
            call.event.set()

    def active_keys(self) -> int:
        """Return the number of distinct operations currently in-flight."""
        with self._lock:
            return len(self._calls)


class _AsyncFlightCall(Generic[V]):
    """State of an in-flight asynchronous call."""

    def __init__(self) -> None:
        self.event = asyncio.Event()
        self.val: Optional[V] = None
        self.err: Optional[BaseException] = None
        self.done: bool = False


class AsyncSingleFlight(Generic[K, V]):
    """AsyncIO-native request coalescing for asynchronous operations."""

    def __init__(self) -> None:
        self._calls: Dict[K, _AsyncFlightCall[V]] = {}
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def do(self, key: K, fn: Callable[[], Awaitable[V]]) -> V:
        """Asynchronously coalesce in-flight coroutines matching the same key."""
        lock = self._get_lock()
        async with lock:
            if key in self._calls:
                call = self._calls[key]
                leader = False
            else:
                call = _AsyncFlightCall[V]()
                self._calls[key] = call
                leader = True

        if not leader:
            await call.event.wait()
            if call.err is not None:
                raise call.err
            return call.val  # type: ignore[return-value]

        try:
            val = await fn()
            call.val = val
            return val
        except BaseException as err:
            call.err = err
            raise
        finally:
            async with lock:
                call.done = True
                self._calls.pop(key, None)
            call.event.set()

    async def active_keys(self) -> int:
        """Return the count of distinct coroutines currently in-flight."""
        lock = self._get_lock()
        async with lock:
            return len(self._calls)
