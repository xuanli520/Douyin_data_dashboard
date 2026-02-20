from __future__ import annotations

from math import ceil
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


def build_pagination_meta(page: int, size: int, total: int) -> dict[str, int | bool]:
    size = max(size, 1)
    page = max(page, 1)
    pages = max(ceil(total / size), 1) if total else 0
    return {
        "page": page,
        "size": size,
        "total": total,
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1 and pages > 0,
    }


class PaginationMeta(BaseModel):
    page: int = Field(ge=1)
    size: int = Field(ge=1)
    total: int = Field(ge=0)
    pages: int = Field(ge=0)
    has_next: bool
    has_prev: bool


class PaginatedItems(BaseModel, Generic[T]):
    items: list[T]
    meta: PaginationMeta


class TrendPoint(BaseModel):
    date: str
    value: float | int


class DimensionScore(BaseModel):
    dimension: str
    score: float
    rank: int
    weight: str


class AlertSummary(BaseModel):
    critical: int
    warning: int
    info: int
    total: int
    unread: int
