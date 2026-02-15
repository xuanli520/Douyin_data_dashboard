from datetime import datetime
from pydantic import BaseModel, Field
from src.audit.schemas import AuditAction, AuditResult


class AuditLogFilters(BaseModel):
    action: AuditAction | None = None
    result: AuditResult | None = None
    actor_id: int | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    ip: str | None = None
    request_id: str | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)
