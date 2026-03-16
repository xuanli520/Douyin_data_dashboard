from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_NESTED_LIST_KEYS = (
    "list",
    "items",
    "records",
    "waiting_list",
    "rows",
    "result",
    "data",
)


def extract_nested_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, Mapping):
        return []

    nested_candidates: list[Mapping[str, Any]] = []
    for key in _NESTED_LIST_KEYS:
        nested = value.get(key)
        if isinstance(nested, list):
            return nested
        if isinstance(nested, Mapping):
            nested_candidates.append(nested)

    for nested in nested_candidates:
        extracted = extract_nested_list(nested)
        if extracted:
            return extracted
    return []
