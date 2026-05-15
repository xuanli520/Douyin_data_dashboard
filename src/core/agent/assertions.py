from __future__ import annotations

import re
from typing import Any

from src.core.agent.exceptions import AssertionFailedError
from src.core.agent.models import AssertionSpec


def evaluate_assertions(
    *,
    assertions: list[AssertionSpec],
    values: dict[str, Any],
) -> list[AssertionSpec]:
    warnings: list[AssertionSpec] = []
    for assertion in assertions:
        passed = _evaluate(assertion, values.get(assertion.source))
        if passed:
            continue
        if assertion.severity == "warning":
            warnings.append(assertion)
            continue
        raise AssertionFailedError(f"assertion failed: {assertion.id}")
    return warnings


def _evaluate(assertion: AssertionSpec, value: Any) -> bool:
    if assertion.kind == "exists":
        return value is not None
    if assertion.kind == "not_empty":
        return not _empty(value)
    if assertion.kind == "equals":
        return value == assertion.expected
    if assertion.kind == "contains":
        return str(assertion.expected) in str(value)
    if assertion.kind == "matches":
        return re.search(str(assertion.expected or ""), str(value or "")) is not None
    if assertion.kind == "url_allowed":
        return bool(value)
    return False


def _empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str | list | dict | tuple | set):
        return len(value) == 0
    return False
