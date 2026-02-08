from typing import Generic, TypeVar
from pydantic import BaseModel, Field


T = TypeVar("T")


class PageMeta(BaseModel):
    page: int = Field(..., ge=1, description="Current page number (1-indexed)")
    size: int = Field(..., ge=1, le=100, description="Items per page")
    total: int = Field(..., ge=0, description="Total item count")
    pages: int = Field(..., ge=0, description="Total page count")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_prev: bool = Field(..., description="Whether there is a previous page")


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
        pages = (total + size - 1) // size if size > 0 else 0
        has_next = page < pages
        has_prev = page > 1
        meta = PageMeta(
            page=page,
            size=size,
            total=total,
            pages=pages,
            has_next=has_next,
            has_prev=has_prev,
        )
        return cls(items=items, meta=meta)
