from __future__ import annotations

from typing import Any

from src.core.agent.browser import BrowserDriver
from src.core.agent.exceptions import ObservationError
from src.core.agent.models import ObservationSpec
from src.core.agent.parsers import parse_value
from src.core.agent.security import validate_locator


def read_observation(
    *,
    driver: BrowserDriver,
    spec: ObservationSpec,
) -> Any:
    if spec.kind == "url":
        value = driver.current_url()
    elif spec.kind == "title":
        value = driver.title()
    elif spec.kind in {"text", "attribute"}:
        if spec.locator is None:
            raise ObservationError(f"observation {spec.id} requires locator")
        validate_locator(spec.locator)
        value = driver.text(spec.locator)
    elif spec.kind in {"table", "list"}:
        if spec.locator is None:
            raise ObservationError(f"observation {spec.id} requires locator")
        validate_locator(spec.locator)
        if spec.kind == "table":
            result = driver.extract_table(spec.locator)
            value = result.data
        else:
            text = driver.text(spec.locator)
            value = _split_lines(text, max_items=spec.max_items)
    else:
        raise ObservationError(f"unsupported observation kind: {spec.kind}")
    parser = spec.parser
    if parser is None and spec.kind in {"table", "list"}:
        parser = "json"
    parsed = parse_value(value, parser)
    if spec.required and _empty(parsed):
        raise ObservationError(f"observation {spec.id} is required")
    return parsed


def read_observations(
    *,
    driver: BrowserDriver,
    observations: dict[str, ObservationSpec],
) -> dict[str, Any]:
    return {
        key: read_observation(driver=driver, spec=spec)
        for key, spec in observations.items()
    }


def _split_lines(text: str, *, max_items: int | None) -> list[str]:
    items = [item.strip() for item in str(text or "").splitlines() if item.strip()]
    if max_items is not None:
        return items[: max(max_items, 0)]
    return items


def _empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str | list | dict | tuple | set):
        return len(value) == 0
    return False
