from __future__ import annotations

import inspect
from typing import Any

try:
    from playwright.async_api import Page
except ImportError:  # pragma: no cover
    Page = Any  # type: ignore[assignment]


async def check_login_status(
    page: Page,
    dom_selector: str = '[data-testid="user-avatar"]',
    dom_timeout_ms: int = 3000,
    api_timeout_seconds: float = 5.0,
) -> bool:
    current_url = str(getattr(page, "url", "") or "").lower()
    if any(token in current_url for token in ("login/common", "/login", "passport")):
        return False

    try:
        await page.wait_for_selector(dom_selector, timeout=dom_timeout_ms)
        return True
    except Exception:
        pass

    request = getattr(page, "request", None)
    if request is None:
        return False
    try:
        response = await request.get(
            "https://fxg.jinritemai.com/ecomauth/loginv1/get_login_subject_count?login_source=doudian_pc_web",
            timeout=api_timeout_seconds * 1000,
        )
        payload = response.json()
        if inspect.isawaitable(payload):
            payload = await payload
        if isinstance(payload, dict):
            code = payload.get("code")
            if code in (0, "0", 200, "200"):
                return True
            if code in (10008, "10008", 401, "401", 403, "403"):
                return False
            return bool(payload.get("data"))
        return bool(getattr(response, "ok", False))
    except Exception:
        return False
