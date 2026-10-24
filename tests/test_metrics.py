"""Tests for CacheMetrics."""

from cacheforge.metrics import CacheMetrics


def test_metrics_counters():
    metrics = CacheMetrics()
    assert metrics.hits == 0
    assert metrics.misses == 0
    assert metrics.total_lookups == 0
    assert metrics.hit_rate == 0.0
    assert metrics.miss_rate == 0.0

    metrics.record_hit()
    metrics.record_hit()
    metrics.record_miss()

    assert metrics.hits == 2
    assert metrics.misses == 1
    assert metrics.total_lookups == 3
    assert round(metrics.hit_rate, 4) == round(2 / 3, 4)
    assert round(metrics.miss_rate, 4) == round(1 / 3, 4)

    metrics.record_set()
    metrics.record_delete()
    metrics.record_eviction(2)
    metrics.record_expiration(3)

    assert metrics.sets == 1
    assert metrics.deletes == 1
    assert metrics.evictions == 2
    assert metrics.expirations == 3

    d = metrics.to_dict()
    assert d["hits"] == 2
    assert d["evictions"] == 2

    metrics.reset()
    assert metrics.total_lookups == 0
    assert metrics.hits == 0
