from __future__ import annotations

from w2.api.cache import ReadOnlyResponseCache


def test_read_cache_is_lru_bounded_and_supports_explicit_invalidation() -> None:
    cache = ReadOnlyResponseCache(max_items=2)
    first = cache.get_or_set("first", {"value": 1})
    cache.get_or_set("second", {"value": 2})
    assert cache.get_or_set("first", {"value": 1}) is first

    cache.get_or_set("third", {"value": 3})

    assert len(cache) == 2
    assert "second" not in cache._items
    assert cache.invalidate("first") is True
    assert cache.invalidate("first") is False
    cache.clear()
    assert len(cache) == 0
