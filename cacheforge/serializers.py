"""Data serialization and compression strategies for persistent caching."""

from __future__ import annotations

import abc
import json
import pickle
import zlib
from typing import Any, Optional


class BaseSerializer(abc.ABC):
    """Abstract Base Class for cache serialization."""

    @abc.abstractmethod
    def serialize(self, value: Any) -> bytes:
        """Serialize an arbitrary Python object into bytes."""
        raise NotImplementedError

    @abc.abstractmethod
    def deserialize(self, data: bytes) -> Any:
        """Deserialize bytes back into a Python object."""
        raise NotImplementedError


class PickleSerializer(BaseSerializer):
    """High-performance serializer using Python's native pickle module."""

    def __init__(self, protocol: int = pickle.HIGHEST_PROTOCOL) -> None:
        self.protocol = protocol

    def serialize(self, value: Any) -> bytes:
        return pickle.dumps(value, protocol=self.protocol)

    def deserialize(self, data: bytes) -> Any:
        return pickle.loads(data)


class JSONSerializer(BaseSerializer):
    """Safe UTF-8 JSON serializer for primitive types and standard collections."""

    def __init__(self, default: Optional[Any] = None) -> None:
        self.default = default

    def serialize(self, value: Any) -> bytes:
        return json.dumps(value, default=self.default, ensure_ascii=False).encode("utf-8")

    def deserialize(self, data: bytes) -> Any:
        return json.loads(data.decode("utf-8"))


class RawBytesSerializer(BaseSerializer):
    """Pass-through serializer for raw bytes or string payloads."""

    def serialize(self, value: Any) -> bytes:
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode("utf-8")
        raise TypeError(f"RawBytesSerializer requires bytes or str, got {type(value)}")

    def deserialize(self, data: bytes) -> Any:
        return data


class CompressedSerializer(BaseSerializer):
    """Decorator serializer that adds zlib compression when payload exceeds min_size.

    Prepends a 1-byte header:
    - 0x00: Raw serialized data (below threshold)
    - 0x01: Compressed with zlib
    """

    FLAG_RAW = b"\x00"
    FLAG_ZLIB = b"\x01"

    def __init__(
        self,
        base_serializer: Optional[BaseSerializer] = None,
        min_size: int = 128,
        level: int = 6,
    ) -> None:
        self.base = base_serializer or PickleSerializer()
        self.min_size = min_size
        self.level = level

    def serialize(self, value: Any) -> bytes:
        raw = self.base.serialize(value)
        if len(raw) < self.min_size:
            return self.FLAG_RAW + raw
        compressed = zlib.compress(raw, level=self.level)
        # Only use compressed if it actually reduced size
        if len(compressed) < len(raw):
            return self.FLAG_ZLIB + compressed
        return self.FLAG_RAW + raw

    def deserialize(self, data: bytes) -> Any:
        if not data:
            return None
        flag = data[:1]
        payload = data[1:]
        if flag == self.FLAG_ZLIB:
            decompressed = zlib.decompress(payload)
            return self.base.deserialize(decompressed)
        elif flag == self.FLAG_RAW:
            return self.base.deserialize(payload)
        else:
            # Backwards compatibility fallback if no flag
            try:
                return self.base.deserialize(data)
            except Exception:
                raise ValueError("Unrecognized compression header flag in cache payload")
