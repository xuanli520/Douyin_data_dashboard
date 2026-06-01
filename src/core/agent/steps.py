from __future__ import annotations

from typing import Any

from src.core.agent.browser import BrowserDriver
from src.core.agent.browser import DriverResult
from src.core.agent.exceptions import AgentError
from src.core.agent.exceptions import BrowserDriverError
from src.core.agent.exceptions import RecipeValidationError
from src.core.agent.models import Step
from src.core.agent.security import validate_locator
from src.core.agent.security import validate_navigation_target
from src.core.agent.security import validate_tool_name


def run_step(
    *,
    driver: BrowserDriver,
    step: Step,
    entrypoint_url: str,
    allowed_origins: list[str],
) -> DriverResult:
    try:
        validate_tool_name(step.action)
        if step.target is not None:
            validate_locator(step.target)
        if step.action == "goto":
            url = str(step.value or entrypoint_url).strip()
            validate_navigation_target_url = validate_navigation_target
            validate_navigation_target_url(url, _policy(allowed_origins))
            return driver.goto(url)
        if step.action == "back":
            return driver.back()
        if step.action == "reload":
            return driver.reload()
        if step.action == "click":
            return driver.click(_require_target(step))
        if step.action == "fill":
            return driver.fill(_require_target(step), str(step.value or ""))
        if step.action == "select":
            return driver.select(_require_target(step), str(step.value or ""))
        if step.action == "wait_visible":
            return driver.wait_visible(
                _require_target(step),
                float(step.timeout_seconds or 30),
            )
        if step.action == "wait_network_idle":
            return driver.wait_network_idle(float(step.timeout_seconds or 30))
        if step.action == "scroll_down":
            return driver.scroll_down(step.value)
        if step.action == "scroll_up":
            return driver.scroll_up(step.value)
        if step.action == "scroll_to_element":
            return driver.scroll_to_element(_require_target(step))
        if step.action == "extract_table":
            return driver.extract_table(_require_target(step))
        if step.action == "extract_list":
            return driver.extract_list(_require_target(step))
        if step.action == "extract_text":
            return driver.extract_text(_require_target(step))
    except AgentError:
        raise
    except Exception as exc:
        raise BrowserDriverError(str(exc)) from exc
    raise RecipeValidationError(f"unsupported action: {step.action}")


def _require_target(step: Step):
    if step.target is None:
        raise RecipeValidationError(f"step {step.id} requires target")
    return step.target


def _policy(allowed_origins: list[str]) -> Any:
    from src.core.agent.models import SecurityPolicy

    return SecurityPolicy(allowed_origins=allowed_origins)
