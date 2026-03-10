from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.exceptions import BusinessException
from src.shared.errors import ErrorCode


def normalize_login_state(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise BusinessException(
            ErrorCode.DATASOURCE_LOGIN_STATE_INVALID,
            "shop dashboard login state must be an object",
        )

    cookies = payload.get("cookies")
    if not isinstance(cookies, list):
        raise BusinessException(
            ErrorCode.DATASOURCE_LOGIN_STATE_INVALID,
            "shop dashboard login state cookies must be a list",
        )

    origins = payload.get("origins")
    if origins is None:
        normalized_origins: list[Any] = []
    elif isinstance(origins, list):
        normalized_origins = origins
    else:
        raise BusinessException(
            ErrorCode.DATASOURCE_LOGIN_STATE_INVALID,
            "shop dashboard login state origins must be a list",
        )

    normalized = dict(payload)
    normalized["cookies"] = cookies
    normalized["origins"] = normalized_origins
    state_version = normalized.get("state_version")
    normalized["state_version"] = str(state_version).strip() if state_version else "v1"
    return normalized


def build_login_state_meta(
    login_state: dict[str, Any],
    *,
    account_id: str,
) -> dict[str, Any]:
    cookie_values = login_state.get("cookies")
    cookie_count = len(cookie_values) if isinstance(cookie_values, list) else 0
    state_version = login_state.get("state_version")
    return {
        "account_id": account_id,
        "cookie_count": cookie_count,
        "state_version": str(state_version).strip() if state_version else "v1",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
