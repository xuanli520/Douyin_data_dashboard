from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ShopSelection:
    all: bool
    shop_ids: list[str]

    def to_payload(self) -> dict[str, Any]:
        if self.all:
            return {"all": True}
        if not self.shop_ids:
            return {"all": False}
        return {
            "all": False,
            "shop_ids": list(self.shop_ids),
            "shop_id": self.shop_ids[0],
        }


def normalize_shop_selection(payload: Mapping[str, Any] | None) -> ShopSelection:
    data = dict(payload or {})
    raw_shop_id = data.get("shop_id")
    raw_shop_ids = data.get("shop_ids")
    raw_all = data.get("all")
    parsed_shop_ids = _parse_shop_ids(raw_shop_ids)
    if not parsed_shop_ids:
        parsed_shop_ids = _parse_shop_ids(raw_shop_id)
    explicit_all = _parse_optional_bool(raw_all)
    contains_all_marker = any(_is_all_marker(item) for item in parsed_shop_ids)
    if explicit_all is True or contains_all_marker:
        return ShopSelection(all=True, shop_ids=[])
    normalized_shop_ids = [item for item in parsed_shop_ids if not _is_all_marker(item)]
    return ShopSelection(all=False, shop_ids=normalized_shop_ids)


def normalize_shop_selection_payload(
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    data = dict(payload or {})
    if not has_explicit_shop_selection(data):
        return data
    selection = normalize_shop_selection(data)
    normalized_payload = dict(data)
    if selection.all:
        normalized_payload["all"] = True
        candidate_shop_ids = _parse_shop_ids(data.get("shop_ids"))
        if not candidate_shop_ids:
            candidate_shop_ids = _parse_shop_ids(data.get("shop_id"))
        candidate_shop_ids = [
            item for item in candidate_shop_ids if not _is_all_marker(item)
        ]
        if candidate_shop_ids:
            normalized_payload["shop_ids"] = list(candidate_shop_ids)
            normalized_payload["shop_id"] = candidate_shop_ids[0]
        else:
            normalized_payload.pop("shop_id", None)
            normalized_payload.pop("shop_ids", None)
    elif selection.shop_ids:
        normalized_payload["all"] = False
        normalized_payload["shop_ids"] = list(selection.shop_ids)
        normalized_payload["shop_id"] = selection.shop_ids[0]
    else:
        normalized_payload["all"] = False
        normalized_payload.pop("shop_id", None)
        normalized_payload.pop("shop_ids", None)
    return normalized_payload


def has_explicit_shop_selection(payload: Mapping[str, Any] | None) -> bool:
    if not isinstance(payload, Mapping):
        return False
    return any(key in payload for key in ("shop_id", "shop_ids", "all"))


def ensure_explicit_shop_selection_valid(payload: Mapping[str, Any] | None) -> None:
    selection = normalize_shop_selection(payload)
    if not selection.all and not selection.shop_ids:
        raise ValueError("No target shops resolved")


def _parse_shop_ids(value: Any) -> list[str]:
    if value is None:
        return []
    items: list[Any]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except ValueError:
                return []
            if isinstance(parsed, list):
                items = list(parsed)
            else:
                items = [text]
        else:
            normalized_text = text.replace(";", ",").replace("|", ",")
            items = [part for part in normalized_text.split(",")]
    elif isinstance(value, list | tuple | set):
        items = list(value)
    else:
        items = [value]
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _parse_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes", "y", "on"}:
            return True
        if text in {"false", "0", "no", "n", "off", ""}:
            return False
    return None


def _is_all_marker(value: str) -> bool:
    return str(value or "").strip().lower() in {"all", "*"}
