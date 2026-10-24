"""CacheForge: Lightweight, zero-dependency caching, tiered storage, and cache stampede protection toolkit for Python."""

from __future__ import annotations

from cacheforge.base import BaseCache, CacheEntry
from cacheforge.decorators import acached, cached
from cacheforge.disk import DiskCache
from cacheforge.fifo import FIFOCache
from cacheforge.lfu import LFUCache
from cacheforge.lru import LRUCache
from cacheforge.metrics import CacheMetrics
from cacheforge.serializers import (
    BaseSerializer,
    CompressedSerializer,
    JSONSerializer,
    PickleSerializer,
    RawBytesSerializer,
)
from cacheforge.singleflight import AsyncSingleFlight, SingleFlight
from cacheforge.tiered import TieredCache
from cacheforge.ttl import SlidingTTLCache, TTLCache

__version__ = "0.1.0"
__author__ = "Hamidreza"
__email__ = "h4midrezam@gmail.com"

__all__ = [
    "__version__",
    "BaseCache",
    "CacheEntry",
    "CacheMetrics",
    "LRUCache",
    "LFUCache",
    "TTLCache",
    "SlidingTTLCache",
    "FIFOCache",
    "DiskCache",
    "TieredCache",
    "SingleFlight",
    "AsyncSingleFlight",
    "cached",
    "acached",
    "BaseSerializer",
    "PickleSerializer",
    "JSONSerializer",
    "RawBytesSerializer",
    "CompressedSerializer",
]
