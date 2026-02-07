from typing import Generic, TypeVar
from pydantic import BaseModel, Field


T = TypeVar("T")


class PageMeta(BaseModel):
    page: int = Field(..., ge=1, description="Current page number (1-indexed)")
    size: int = Field(..., ge=1, le=100, description="Items per page")
    total: int = Field(..., ge=0, description="Total item count")
    pages: int = Field(..., ge=0, description="Total page count")


class PaginationParams(BaseModel):
    page: int = Field(1, ge=1, description="Page number")
    size: int = Field(20, ge=1, le=100, description="Page size")

    def offset(self) -> int:
        return (self.page - 1) * self.size


class PaginatedData(BaseModel, Generic[T]):
    items: list[T]
    meta: PageMeta

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int,
        size: int,
    ) -> "PaginatedData[T]":
        pages = (total + size - 1) // size if total > 0 else 0
        meta = PageMeta(page=page, size=size, total=total, pages=pages)
        return cls(items=items, meta=meta)


def create_paginated_response(
    items: list[T],
    total: int,
    page: int,
    size: int,
) -> PaginatedData[T]:
    return PaginatedData.create(items=items, total=total, page=page, size=size)
