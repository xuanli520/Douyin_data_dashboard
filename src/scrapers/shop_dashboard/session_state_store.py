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

    def exists_bundle(self, account_id: str, shop_id: str) -> bool:
        return self._bundle_path(account_id, shop_id).exists()

    def save_bundle(
        self, account_id: str, shop_id: str, bundle: dict[str, Any]
    ) -> Path:
        normalized_bundle = self._normalize_bundle_payload(shop_id, bundle)
        target = self._bundle_path(account_id, shop_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_file = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
        )
        temp_path = Path(temp_file)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    normalized_bundle,
                    handle,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                handle.flush()
                os.fsync(handle.fileno())
            temp_path.replace(target)
        finally:
            if temp_path.exists():
                temp_path.unlink()
        return target

    def load_bundle(self, account_id: str, shop_id: str) -> dict[str, Any] | None:
        target = self._bundle_path(account_id, shop_id)
        if not target.exists():
            return None
        try:
            content = target.read_text(encoding="utf-8")
            payload = json.loads(content)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return None
        if isinstance(payload, dict):
            return self._normalize_bundle_payload(shop_id, payload)
        return None

    def invalidate_bundle(self, account_id: str, shop_id: str) -> None:
        target = self._bundle_path(account_id, shop_id)
        if target.exists():
            target.unlink()

    def load_bundle_cookie_mapping(
        self, account_id: str, shop_id: str
    ) -> dict[str, str]:
        bundle = self.load_bundle(account_id, shop_id)
        if not bundle:
            return {}
        cookies = bundle.get("cookies")
        if not isinstance(cookies, dict):
            return {}
        return {
            str(key): str(value)
            for key, value in cookies.items()
            if key is not None and value is not None
        }

    def _path(self, account_id: str) -> Path:
        safe_name = str(account_id).replace("\\", "_").replace("/", "_").strip()
        return self._base_dir / f"{safe_name}.json"

    def _bundle_path(self, account_id: str, shop_id: str) -> Path:
        safe_account_id = str(account_id).replace("\\", "_").replace("/", "_").strip()
        safe_shop_id = str(shop_id).replace("\\", "_").replace("/", "_").strip()
        return self._base_dir / "bundles" / safe_account_id / f"{safe_shop_id}.json"

    def _normalize_bundle_payload(
        self, shop_id: str, bundle: dict[str, Any]
    ) -> dict[str, Any]:
        cookies = bundle.get("cookies")
        if isinstance(cookies, dict):
            normalized_cookies = {
                str(key): str(value)
                for key, value in cookies.items()
                if key is not None and value is not None
            }
        else:
            normalized_cookies = {}
        common_query = bundle.get("common_query")
        if isinstance(common_query, dict):
            normalized_common_query = {
                str(key): value
                for key, value in common_query.items()
                if key is not None and value is not None
            }
        else:
            normalized_common_query = {}
        validated_shop_id = (
            str(bundle.get("validated_shop_id") or "").strip() or str(shop_id).strip()
        )
        validated_at = str(bundle.get("validated_at") or "").strip()
        session_version = str(bundle.get("session_version") or "").strip() or "1"
        return {
            "cookies": normalized_cookies,
            "common_query": normalized_common_query,
            "validated_shop_id": validated_shop_id,
            "validated_at": validated_at,
            "session_version": session_version,
        }
