from __future__ import annotations

from pathlib import Path
from uuid import uuid4


def new_session_id() -> str:
    return uuid4().hex


def build_storage_state_path(base_dir: str | Path, session_id: str) -> Path:
    root = Path(base_dir)
    target = root / f"{_safe_segment(session_id)}.json"
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    if (
        resolved_root not in resolved_target.parents
        and resolved_target != resolved_root
    ):
        raise ValueError("storage state path escapes base directory")
    return target


def _safe_segment(value: str) -> str:
    normalized = str(value or "").replace("\\", "_").replace("/", "_").strip()
    return normalized or "session"
