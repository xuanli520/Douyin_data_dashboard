from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlparse

from src.core.agent.exceptions import SecurityPolicyError
from src.core.agent.models import LocatorSpec
from src.core.agent.models import SecurityPolicy

DEFAULT_ALLOWED_TOOLS = frozenset(
    {
        "goto",
        "back",
        "reload",
        "click",
        "fill",
        "select",
        "scroll_down",
        "scroll_up",
        "scroll_to_element",
        "wait_visible",
        "wait_network_idle",
        "get_current_url",
        "get_page_title",
        "get_element_text",
        "extract_table",
        "extract_list",
        "extract_text",
        "done",
    }
)
DEFAULT_BLOCKED_TOOLS = frozenset(
    {"submit_form", "click_confirm", "click_delete", "evaluate", "download"}
)
DEFAULT_BLOCKED_PATTERNS = (
    "delete",
    "remove",
    "confirm",
    "submit",
    "javascript:",
    "eval",
    "download",
    "refund",
    "payment",
    "settlement",
    "checkout",
)


def validate_tool_name(tool_name: str) -> str:
    normalized = str(tool_name or "").strip()
    if normalized in DEFAULT_BLOCKED_TOOLS or normalized not in DEFAULT_ALLOWED_TOOLS:
        raise SecurityPolicyError(f"tool is not allowed: {normalized}")
    return normalized


def validate_url_allowed(url: str, allowed_origins: Iterable[str]) -> str:
    parsed = urlparse(str(url or "").strip())
    origin = (
        f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    )
    allowed = {str(item).rstrip("/") for item in allowed_origins if str(item).strip()}
    if not origin or origin.rstrip("/") not in allowed:
        raise SecurityPolicyError(f"url origin is not allowed: {url}")
    return url


def validate_locator(locator: LocatorSpec) -> LocatorSpec:
    lowered = locator.value.casefold()
    if any(pattern in lowered for pattern in DEFAULT_BLOCKED_PATTERNS):
        raise SecurityPolicyError("locator contains a blocked pattern")
    return locator


def validate_navigation_target(url: str, security_policy: SecurityPolicy) -> str:
    return validate_url_allowed(url, security_policy.allowed_origins)


def validate_page_risk(url: str, title: str, snapshot_text: str) -> None:
    haystack = "\n".join((url, title, snapshot_text)).casefold()
    if any(pattern in haystack for pattern in DEFAULT_BLOCKED_PATTERNS):
        raise SecurityPolicyError("page content contains a blocked pattern")
