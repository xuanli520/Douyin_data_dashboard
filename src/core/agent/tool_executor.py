from __future__ import annotations

from typing import Any

from src.core.agent.tools import ToolCall, ToolRegistry


class ToolExecutor:
    def __init__(
        self,
        driver: Any,
        *,
        registry: ToolRegistry | None = None,
        security: Any | None = None,
    ) -> None:
        self._driver = driver
        self._registry = registry or ToolRegistry()
        self._security = security

    def execute(
        self,
        tool_call: ToolCall | dict[str, Any],
        *,
        security_policy: Any | None = None,
    ) -> Any:
        validated = self._registry.validate_tool_call(tool_call)
        self._validate_tool_call(validated, security_policy=security_policy)
        if validated.name == "done":
            return {
                "status": "done",
                "message": validated.arguments.get("message"),
            }
        return self._dispatch(validated)

    def capture_observation(
        self,
        *,
        tool_results: list[dict[str, Any]] | None = None,
        security_policy: Any | None = None,
    ) -> dict[str, Any]:
        current_url = self._safe_driver_call("get_current_url")
        page_title = self._safe_driver_call("get_page_title")
        snapshot_text = self._safe_driver_call("get_snapshot")
        if snapshot_text is None:
            snapshot_text = self._safe_driver_call("snapshot")
        screenshot_artifact_id = self._safe_driver_call("capture_screenshot")
        if screenshot_artifact_id is None:
            screenshot_artifact_id = self._safe_driver_call("take_screenshot")
        self._call_security_validator(
            "validate_page_risk",
            current_url,
            page_title,
            snapshot_text,
        )
        return {
            "current_url": current_url,
            "page_title": page_title,
            "screenshot_artifact_id": screenshot_artifact_id,
            "snapshot_text": snapshot_text,
            "tool_results": list(tool_results or []),
        }

    def _dispatch(self, tool_call: ToolCall) -> Any:
        arguments = tool_call.arguments
        if tool_call.name == "goto":
            return self._require_driver_method("goto")(arguments["url"])
        if tool_call.name == "back":
            return self._require_driver_method("back")()
        if tool_call.name == "reload":
            return self._require_driver_method("reload")()
        if tool_call.name == "click":
            return self._require_driver_method("click")(arguments["locator"])
        if tool_call.name == "fill":
            return self._require_driver_method("fill")(arguments["locator"], arguments["value"])
        if tool_call.name == "select":
            return self._require_driver_method("select")(arguments["locator"], arguments["value"])
        if tool_call.name == "scroll_down":
            return self._require_driver_method("scroll_down")(arguments.get("amount"))
        if tool_call.name == "scroll_up":
            return self._require_driver_method("scroll_up")(arguments.get("amount"))
        if tool_call.name == "scroll_to_element":
            return self._require_driver_method("scroll_to_element")(arguments["locator"])
        if tool_call.name == "wait_visible":
            return self._require_driver_method("wait_visible")(
                arguments["locator"],
                arguments.get("timeout_seconds"),
            )
        if tool_call.name == "wait_network_idle":
            return self._require_driver_method("wait_network_idle")(arguments.get("timeout_seconds"))
        if tool_call.name == "get_current_url":
            return self._require_driver_method("get_current_url")()
        if tool_call.name == "get_page_title":
            return self._require_driver_method("get_page_title")()
        if tool_call.name == "get_element_text":
            return self._require_driver_method("get_element_text")(arguments["locator"])
        if tool_call.name == "extract_table":
            return self._require_driver_method("extract_table")(arguments["locator"])
        if tool_call.name == "extract_list":
            return self._require_driver_method("extract_list")(arguments["locator"])
        if tool_call.name == "extract_text":
            return self._require_driver_method("extract_text")(arguments["locator"])
        raise ValueError(f"unsupported tool: {tool_call.name}")

    def _validate_tool_call(
        self,
        tool_call: ToolCall,
        *,
        security_policy: Any | None = None,
    ) -> None:
        self._call_security_validator("validate_tool_name", tool_call.name)
        locator = tool_call.arguments.get("locator")
        if locator is not None:
            self._call_security_validator("validate_locator", locator)
        url = tool_call.arguments.get("url")
        if url is not None:
            self._call_navigation_validator(url, security_policy)

    def _call_navigation_validator(self, url: str, security_policy: Any | None) -> None:
        validator = self._get_security_validator("validate_navigation_target")
        if validator is not None:
            validator(url, security_policy)
            return
        fallback = self._get_security_validator("validate_url_allowed")
        if fallback is None:
            return
        allowed_origins = None
        if isinstance(security_policy, dict):
            allowed_origins = security_policy.get("allowed_origins")
        elif security_policy is not None:
            allowed_origins = getattr(security_policy, "allowed_origins", None)
        fallback(url, allowed_origins)

    def _call_security_validator(self, name: str, *args: Any) -> None:
        validator = self._get_security_validator(name)
        if validator is None:
            return
        validator(*args)

    def _get_security_validator(self, name: str) -> Any | None:
        if self._security is None:
            return None
        return getattr(self._security, name, None)

    def _require_driver_method(self, name: str) -> Any:
        method = getattr(self._driver, name, None)
        if method is None:
            raise AttributeError(f"driver does not implement {name}")
        return method

    def _safe_driver_call(self, name: str) -> Any:
        method = getattr(self._driver, name, None)
        if method is None:
            return None
        return method()
