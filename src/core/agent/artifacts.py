from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def build_artifact_path(base_dir: str | Path, session_id: str, filename: str) -> Path:
    root = Path(base_dir)
    target = root / _safe_segment(session_id) / Path(filename).name
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    if resolved_root not in resolved_target.parents and resolved_target != resolved_root:
        raise ValueError("artifact path escapes base directory")
    return target


def cleanup_expired_artifacts(
    base_dir: str | Path,
    ttl_seconds: int,
    *,
    now: datetime | None = None,
) -> list[Path]:
    root = Path(base_dir)
    if not root.exists():
        return []
    cutoff = (now or datetime.now(tz=UTC)) - timedelta(seconds=max(ttl_seconds, 0))
    removed: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if modified_at > cutoff:
            continue
        path.unlink()
        removed.append(path)
    return removed


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _redacted_value(str(key), item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    return value


def _redacted_value(key: str, value: Any) -> Any:
    lowered = key.casefold()
    if any(token in lowered for token in ("cookie", "authorization", "token")):
        return "[redacted]"
    return sanitize_payload(value)


def _safe_segment(value: str) -> str:
    normalized = str(value or "").replace("\\", "_").replace("/", "_").strip()
    return normalized or "session"
