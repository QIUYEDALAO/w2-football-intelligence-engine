from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from w2.models.independent import artifact_hash


@dataclass(frozen=True)
class CachedRead:
    etag: str
    payload: Any


class ReadOnlyResponseCache:
    def __init__(self) -> None:
        self._items: dict[str, CachedRead] = {}

    def get_or_set(self, key: str, payload: Any) -> CachedRead:
        etag = artifact_hash(payload)
        cached = self._items.get(key)
        if cached and cached.etag == etag:
            return cached
        value = CachedRead(etag=etag, payload=payload)
        self._items[key] = value
        return value


read_cache = ReadOnlyResponseCache()
