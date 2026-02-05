from typing import NamedTuple
from dataclasses import dataclass


@dataclass
class ParsedRow:
    row_number: int
    raw_data: dict[str, str]
    fields: list[str]
    is_valid: bool = True
    error_message: str | None = None


class ParseProgress(NamedTuple):
    current_row: int
    total_rows: int | None
    percentage: float
    is_complete: bool
    file_path: str


__all__ = ["ParsedRow", "ParseProgress"]
