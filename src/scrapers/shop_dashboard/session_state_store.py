from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class SessionStateStore:
    def __init__(self, base_dir: str | Path) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def exists(self, account_id: str) -> bool:
        return self._path(account_id).exists()

    def save(self, account_id: str, state: dict[str, Any]) -> Path:
        target = self._path(account_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_file = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
        )
        temp_path = Path(temp_file)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            temp_path.replace(target)
        finally:
            if temp_path.exists():
                temp_path.unlink()
        return target

    def load(self, account_id: str) -> dict[str, Any] | None:
        target = self._path(account_id)
        if not target.exists():
            return None
        try:
            content = target.read_text(encoding="utf-8")
            payload = json.loads(content)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return None
        if isinstance(payload, dict):
            return payload
        return None

    def load_cookie_mapping(self, account_id: str) -> dict[str, str]:
        payload = self.load(account_id)
        if not payload:
            return {}
        cookies = payload.get("cookies")
        if not isinstance(cookies, list):
            return {}
        mapping: dict[str, str] = {}
        for item in cookies:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            value = item.get("value")
            if name is None or value is None:
                continue
            mapping[str(name)] = str(value)
        return mapping

    def _path(self, account_id: str) -> Path:
        safe_name = str(account_id).replace("\\", "_").replace("/", "_").strip()
        return self._base_dir / f"{safe_name}.json"
