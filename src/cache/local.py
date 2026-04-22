from collections import OrderedDict
from time import time


class LocalCache:
    def __init__(self, max_entries: int = 10000) -> None:
        self._store: OrderedDict[str, tuple[str, float | None]] = OrderedDict()
        self._max_entries = max(max_entries, 1)

    def _is_expired(self, expire_at: float | None) -> bool:
        if expire_at is None:
            return False
        return time() > expire_at

    def _compact(self) -> None:
        if len(self._store) <= self._max_entries:
            return
        expired_keys = [
            key
            for key, (_, expire_at) in self._store.items()
            if self._is_expired(expire_at)
        ]
        for key in expired_keys:
            self._store.pop(key, None)
        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)

    def _cleanup_expired(self, key: str) -> None:
        if key in self._store:
            _, expire_at = self._store[key]
            if self._is_expired(expire_at):
                self._store.pop(key, None)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        if ttl is not None and ttl <= 0:
            raise ValueError("ttl must be greater than 0")
        expire_at = time() + ttl if ttl is not None else None
        self._store.pop(key, None)
        self._store[key] = (value, expire_at)
        self._compact()

    async def get(self, key: str) -> str | None:
        self._cleanup_expired(key)
        if key not in self._store:
            return None
        value, _ = self._store[key]
        self._store.move_to_end(key)
        return value

    async def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    async def exists(self, key: str) -> bool:
        self._cleanup_expired(key)
        exists = key in self._store
        if exists:
            self._store.move_to_end(key)
        return exists

    async def close(self) -> None:
        self._store.clear()
