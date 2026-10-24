"""Tests for data serializers and compression."""

import pytest
from cacheforge.serializers import (
    CompressedSerializer,
    JSONSerializer,
    PickleSerializer,
    RawBytesSerializer,
)


def test_pickle_serializer():
    ser = PickleSerializer()
    obj = {"num": 42, "list": [1, 2, 3], "nested": {"a": True}}
    data = ser.serialize(obj)
    assert isinstance(data, bytes)
    assert ser.deserialize(data) == obj


def test_json_serializer():
    ser = JSONSerializer()
    obj = {"hello": "world", "numbers": [10, 20]}
    data = ser.serialize(obj)
    assert isinstance(data, bytes)
    assert ser.deserialize(data) == obj


def test_raw_bytes_serializer():
    ser = RawBytesSerializer()
    raw = b"raw binary content"
    assert ser.serialize(raw) == raw
    assert ser.deserialize(raw) == raw

    # String encoding
    assert ser.serialize("unicode text") == b"unicode text"

    with pytest.raises(TypeError):
        ser.serialize(12345)


def test_compressed_serializer_small_payload():
    ser = CompressedSerializer(min_size=128)
    small_obj = {"a": 1}
    data = ser.serialize(small_obj)
    assert data.startswith(CompressedSerializer.FLAG_RAW)
    assert ser.deserialize(data) == small_obj


def test_compressed_serializer_large_repetitive_payload():
    ser = CompressedSerializer(min_size=32)
    large_obj = {"text": "repeated string " * 500}
    data = ser.serialize(large_obj)
    # Highly compressible, should be compressed
    assert data.startswith(CompressedSerializer.FLAG_ZLIB)
    assert ser.deserialize(data) == large_obj


def test_compressed_serializer_empty_and_fallback():
    ser = CompressedSerializer()
    assert ser.deserialize(b"") is None

    # Unflagged fallback
    pickle_ser = PickleSerializer()
    raw_pickle = pickle_ser.serialize({"legacy": True})
    assert ser.deserialize(raw_pickle) == {"legacy": True}
