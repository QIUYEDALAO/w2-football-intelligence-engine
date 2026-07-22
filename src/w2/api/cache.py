from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import Any

from w2.models.independent import artifact_hash


@dataclass(frozen=True)
class CachedRead:
    etag: str
    payload: Any


class ReadOnlyResponseCache:
    def __init__(self, *, max_items: int = 2048) -> None:
        if max_items < 1:
            raise ValueError("max_items must be positive")
        self.max_items = max_items
        self._items: OrderedDict[str, CachedRead] = OrderedDict()
        self._lock = RLock()

    def get_or_set(self, key: str, payload: Any) -> CachedRead:
        etag = artifact_hash(payload)
        with self._lock:
            cached = self._items.get(key)
            if cached and cached.etag == etag:
                self._items.move_to_end(key)
                return cached
            value = CachedRead(etag=etag, payload=payload)
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)
            return value

    def invalidate(self, key: str) -> bool:
        with self._lock:
            return self._items.pop(key, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


read_cache = ReadOnlyResponseCache()
