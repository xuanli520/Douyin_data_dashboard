from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


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
