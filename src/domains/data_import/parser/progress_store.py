import json
from datetime import datetime, timezone
from typing import NamedTuple
from json import JSONDecodeError


class ProgressData(NamedTuple):
    file_id: str
    file_path: str
    file_type: str
    current_row: int
    total_rows: int
    last_updated: str
    file_hash: str


class ParseProgressStore:
    def __init__(self, redis_cache):
        self._cache = redis_cache
        self._prefix = "data_import:progress:"

    def _key(self, file_id: str) -> str:
        return f"{self._prefix}{file_id}"

    async def save_progress(
        self,
        file_id: str,
        file_path: str,
        file_type: str,
        current_row: int,
        total_rows: int,
        file_hash: str,
        ttl: int = 86400,
    ) -> None:
        data = {
            "file_id": file_id,
            "file_path": file_path,
            "file_type": file_type,
            "current_row": current_row,
            "total_rows": total_rows,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "file_hash": file_hash,
        }
        await self._cache.set(self._key(file_id), json.dumps(data), ttl)

    async def get_progress(self, file_id: str) -> ProgressData | None:
        raw = await self._cache.get(self._key(file_id))
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return ProgressData(**data)
        except (JSONDecodeError, KeyError):
            return None

    async def delete_progress(self, file_id: str) -> None:
        await self._cache.delete(self._key(file_id))
