from fastapi import APIRouter, Depends, Query, Request
from src.auth.rbac import require_permissions
from src.auth.permissions import AuditPermission
from src.audit.service import AuditService, get_audit_service, extract_client_info
from src.audit.filters import AuditLogFilters
from src.shared.schemas import PaginatedData
from src.audit.schemas import AuditAction, AuditResult
from src.audit.dependencies import generate_request_id

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", response_model=PaginatedData[dict])
async def list_audit_logs(
    request: Request,
    audit_service: AuditService = Depends(get_audit_service),
    action: str | None = Query(None),
    result: str | None = Query(None),
    actor_id: int | None = Query(None),
    resource_type: str | None = Query(None),
    resource_id: str | None = Query(None),
    ip: str | None = Query(None),
    request_id_filter: str | None = Query(None),
    occurred_from: str | None = Query(None),
    occurred_to: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _=Depends(require_permissions(AuditPermission.READ, bypass_superuser=True)),
    request_id: str = Depends(generate_request_id),
):
    filters = AuditLogFilters(
        action=action,
        result=result,
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        ip=ip,
        request_id=request_id_filter,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        page=page,
        size=size,
    )
    items, total = await audit_service.list_logs(filters)
    user_agent, ip = extract_client_info(request)
    await audit_service.log(
        action=AuditAction.PROTECTED_RESOURCE_ACCESS,
        result=AuditResult.SUCCESS,
        actor_id=None,
        request_id=request_id,
        user_agent=user_agent,
        ip=ip,
        resource_type="audit_log",
        extra={
            "filters": filters.model_dump(),
            "total": total,
        },
    )
    return PaginatedData.create(
        items=[i.model_dump() for i in items], total=total, page=page, size=size
    )


@router.get("/logins", response_model=PaginatedData[dict])
async def list_login_audit_logs(
    request: Request,
    audit_service: AuditService = Depends(get_audit_service),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _=Depends(require_permissions(AuditPermission.READ, bypass_superuser=True)),
    request_id: str = Depends(generate_request_id),
):
    filters = AuditLogFilters(
        actions=[
            AuditAction.LOGIN,
            AuditAction.LOGOUT,
            AuditAction.REFRESH,
            AuditAction.REGISTER,
        ],
        page=page,
        size=size,
    )
    items, total = await audit_service.list_logs(filters)
    user_agent, ip = extract_client_info(request)
    await audit_service.log(
        action=AuditAction.PROTECTED_RESOURCE_ACCESS,
        result=AuditResult.SUCCESS,
        actor_id=None,
        request_id=request_id,
        user_agent=user_agent,
        ip=ip,
        resource_type="audit_log",
        extra={
            "filters": filters.model_dump(),
            "total": total,
        },
    )
    return PaginatedData.create(
        items=[i.model_dump() for i in items], total=total, page=page, size=size
    )
