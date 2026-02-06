from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ImportUploadResponse(BaseModel):
    id: int
    file_name: str
    file_size: int
    status: str
    created_at: datetime


class ImportParseResponse(BaseModel):
    id: int
    total_rows: int
    preview: list[dict[str, Any]] = Field(default_factory=list)


class FieldMappingRequest(BaseModel):
    mappings: dict[str, str]
    target_fields: list[str]


class ImportMappingResponse(BaseModel):
    id: int
    status: str


class ImportValidateResponse(BaseModel):
    id: int
    total_rows: int
    passed: int
    failed: int
    errors_by_field: dict[str, int]
    warnings_by_field: dict[str, int]


class ImportConfirmResponse(BaseModel):
    id: int
    total: int
    success: int
    failed: int
    errors: list[dict[str, Any]]


class ImportHistoryItem(BaseModel):
    id: int
    file_name: str
    status: str
    total_rows: int
    success_rows: int
    failed_rows: int
    created_at: datetime


class ImportHistoryResponse(BaseModel):
    items: list[ImportHistoryItem]
    total: int
    page: int
    size: int


class ImportDetailResponse(BaseModel):
    id: int
    file_name: str
    file_size: int
    status: str
    field_mapping: dict[str, str] | None
    total_rows: int
    success_rows: int
    failed_rows: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime | None


class ImportCancelResponse(BaseModel):
    id: int
    status: str
    message: str


class ImportUploadRequest(BaseModel):
    pass
