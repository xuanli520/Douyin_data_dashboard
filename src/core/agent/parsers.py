from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from src.core.agent.exceptions import ObservationError

Parser = Callable[[Any], Any]


def parse_text(value: Any) -> str:
    return str(value or "").strip()


def parse_number(value: Any) -> float:
    text = parse_text(value).replace(",", "")
    if not text:
        raise ObservationError("number value is empty")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if match is None:
        raise ObservationError("number value is invalid")
    return float(match.group(0))


def parse_integer(value: Any) -> int:
    return int(parse_number(value))


def parse_boolean(value: Any) -> bool:
    text = parse_text(value).casefold()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    raise ObservationError("boolean value is invalid")


def parse_date(value: Any) -> str:
    text = parse_text(value)
    return date.fromisoformat(text).isoformat()


def parse_datetime(value: Any) -> str:
    text = parse_text(value)
    return datetime.fromisoformat(text).isoformat()


def parse_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


PARSERS: dict[str, Parser] = {
    "text": parse_text,
    "number": parse_number,
    "integer": parse_integer,
    "boolean": parse_boolean,
    "date": parse_date,
    "datetime": parse_datetime,
    "json": parse_json,
}


def parse_value(value: Any, parser: str | None) -> Any:
    parser_name = str(parser or "text").strip() or "text"
    parse = PARSERS.get(parser_name)
    if parse is None:
        raise ObservationError(f"unknown parser: {parser_name}")
    return parse(value)
