"""Tests for SingleFlight and AsyncSingleFlight."""

import asyncio
import threading
import time
import pytest
from cacheforge.singleflight import AsyncSingleFlight, SingleFlight


def test_singleflight_coalescing():
    flight = SingleFlight[str, int]()
    executions = 0
    lock = threading.Lock()

    def expensive_work():
        nonlocal executions
        with lock:
            executions += 1
        time.sleep(0.08)
        return 42

    threads = []
    results = [None] * 5

    def worker(idx):
        results[idx] = flight.do("shared_key", expensive_work)

    for i in range(5):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # All 5 threads must get the result 42, but the function must run only ONCE!
    assert results == [42, 42, 42, 42, 42]
    assert executions == 1


def test_singleflight_exception_propagation():
    flight = SingleFlight[str, int]()

    def failing_work():
        raise ValueError("computation failed")

    with pytest.raises(ValueError, match="computation failed"):
        flight.do("error_key", failing_work)


def test_async_singleflight_coalescing():
    flight = AsyncSingleFlight[str, str]()
    executions = 0

    async def expensive_coro():
        nonlocal executions
        executions += 1
        await asyncio.sleep(0.05)
        return "async_result"

    async def _test():
        tasks = [flight.do("async_key", expensive_coro) for _ in range(5)]
        results = await asyncio.gather(*tasks)
        assert results == ["async_result"] * 5
        assert executions == 1

    asyncio.run(_test())


def test_async_singleflight_exception_propagation():
    flight = AsyncSingleFlight[str, int]()

    async def failing_coro():
        await asyncio.sleep(0.01)
        raise RuntimeError("coro exception")

    async def _test():
        with pytest.raises(RuntimeError, match="coro exception"):
            await flight.do("err_key", failing_coro)

    asyncio.run(_test())
