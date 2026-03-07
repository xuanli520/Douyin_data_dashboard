from __future__ import annotations

import json
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
        target.write_text(
            json.dumps(state, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        return target

    def load(self, account_id: str) -> dict[str, Any] | None:
        target = self._path(account_id)
        if not target.exists():
            return None
        content = target.read_text(encoding="utf-8")
        payload = json.loads(content)
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
