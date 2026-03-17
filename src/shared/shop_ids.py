from __future__ import annotations

from typing import Any


def normalize_shop_ids(
    value: Any,
    *,
    dedupe: bool = True,
) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates = [part for token in value.split(",") for part in token.split("|")]
    elif isinstance(value, list | tuple | set):
        candidates = list(value)
    else:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text:
            continue
        if dedupe:
            if text in seen:
                continue
            seen.add(text)
        normalized.append(text)
    return normalized
