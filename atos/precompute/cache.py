"""内存 LRU 缓存"""
from collections import OrderedDict
from threading import Lock
from typing import Any, Callable, Optional


class LRUCache:
    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.cache = OrderedDict()
        self.lock = Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str, loader: Optional[Callable] = None) -> Any:
        with self.lock:
            if key in self.cache:
                self.hits += 1
                self.cache.move_to_end(key)
                return self.cache[key]
            self.misses += 1
            if loader is not None:
                value = loader()
                self._put(key, value)
                return value
            return None

    def put(self, key: str, value: Any):
        with self.lock:
            self._put(key, value)

    def _put(self, key, value):
        if len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)
        self.cache[key] = value

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hits / total if total > 0 else 0,
            "size": len(self.cache),
            "max_size": self.max_size,
        }
