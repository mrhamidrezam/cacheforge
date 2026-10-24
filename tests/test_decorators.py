"""Tests for @cached and @acached decorators."""

import asyncio
import time
import pytest
from cacheforge.decorators import acached, cached
from cacheforge.lru import LRUCache


def test_cached_sync_decorator():
    calls = 0

    @cached()
    def get_user_data(user_id: int, flag: bool = True):
        nonlocal calls
        calls += 1
        return {"id": user_id, "active": flag}

    r1 = get_user_data(101, flag=True)
    r2 = get_user_data(101, flag=True)
    assert r1 == r2
    assert calls == 1

    # Different arguments
    r3 = get_user_data(102, flag=True)
    assert calls == 2

    # Invalidate specific key
    assert get_user_data.invalidate(101, flag=True) is True
    r4 = get_user_data(101, flag=True)
    assert calls == 3

    # Cache clear
    get_user_data.cache_clear()
    assert len(get_user_data.cache) == 0


def test_cached_unless_condition():
    calls = 0

    @cached(unless=lambda res: res is None)
    def find_item(item_id: int):
        nonlocal calls
        calls += 1
        if item_id == 0:
            return None
        return f"item_{item_id}"

    # None result should not be cached
    assert find_item(0) is None
    assert find_item(0) is None
    assert calls == 2

    # Non-None should be cached
    assert find_item(1) == "item_1"
    assert find_item(1) == "item_1"
    assert calls == 3


def test_cached_custom_key_builder():
    cache = LRUCache(maxsize=10)

    @cached(cache=cache, key_builder=lambda fn, args, kwargs: f"custom:{args[0]}")
    def square(n: int, ignored_opt: str = "ignore"):
        return n * n

    assert square(5, ignored_opt="a") == 25
    assert square(5, ignored_opt="b") == 25
    assert "custom:5" in cache


def test_cached_ttl():
    @cached(ttl=0.05)
    def fetch_time():
        return time.time()

    t1 = fetch_time()
    t2 = fetch_time()
    assert t1 == t2

    time.sleep(0.08)
    t3 = fetch_time()
    assert t3 > t1


def test_acached_async_decorator():
    calls = 0

    @acached()
    async def async_fetch(resource_id: str):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return f"payload_{resource_id}"

    async def _test():
        nonlocal calls
        v1 = await async_fetch("res_1")
        v2 = await async_fetch("res_1")
        assert v1 == v2
        assert calls == 1

        # Invalidation
        assert async_fetch.invalidate("res_1") is True
        v3 = await async_fetch("res_1")
        assert calls == 2

        # Cache info
        info = async_fetch.cache_info()
        assert "hits" in info["metrics"]

    asyncio.run(_test())


def test_acached_non_coro_error():
    with pytest.raises(TypeError, match="@acached can only decorate coroutine"):
        @acached()
        def sync_fn():
            return 1
