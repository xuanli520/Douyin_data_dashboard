from typing import Any

from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query, Request

from src.api.v1.mock_data import (
    build_task_action,
    build_task_create,
    build_task_execution_detail,
    build_task_executions,
    build_task_retry,
    build_tasks,
)
from src.audit import AuditService, get_audit_service
from src.audit.dependencies import generate_request_id
from src.audit.schemas import AuditAction, AuditResult
from src.audit.service import extract_client_info
from src.auth import User, current_user
from src.auth.permissions import TaskPermission
from src.auth.rbac import require_permissions
from src.core.endpoint_status import in_development
from src.exceptions import EndpointInDevelopmentException

router = APIRouter(prefix="/tasks", tags=["task"])
EXPECTED_RELEASE = "2026-04-30"


class TaskCreatePayload(BaseModel):
    name: str
    task_type: str
    config: dict[str, Any] | None = None


@router.get("")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def list_tasks(
    status: str | None = Query(default=None),
    task_type: str | None = Query(default=None),
    date_range: str | None = Query(default="30d"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_tasks(
            status=status,
            task_type=task_type,
            date_range=date_range,
            page=page,
            size=size,
        ),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.post("")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def create_task(
    request: Request,
    payload: TaskCreatePayload,
    user: User = Depends(current_user),
    audit_service: AuditService = Depends(get_audit_service),
    request_id: str = Depends(generate_request_id),
    _=Depends(require_permissions(TaskPermission.CREATE, bypass_superuser=True)),
):
    user_agent, ip = extract_client_info(request)
    await audit_service.log(
        action=AuditAction.TASK_CREATE,
        result=AuditResult.SUCCESS,
        actor_id=user.id,
        resource_type="task",
        resource_id=payload.name,
        request_id=request_id,
        user_agent=user_agent,
        ip=ip,
        extra={"task_type": payload.task_type, "name": payload.name, "is_mock": True},
    )
    raise EndpointInDevelopmentException(
        data=build_task_create(payload.model_dump()),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.post("/{task_id}/run")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def run_task(
    request: Request,
    task_id: int,
    user: User = Depends(current_user),
    audit_service: AuditService = Depends(get_audit_service),
    request_id: str = Depends(generate_request_id),
    _=Depends(require_permissions(TaskPermission.EXECUTE, bypass_superuser=True)),
):
    user_agent, ip = extract_client_info(request)
    await audit_service.log(
        action=AuditAction.TASK_RUN,
        result=AuditResult.SUCCESS,
        actor_id=user.id,
        resource_type="task",
        resource_id=str(task_id),
        request_id=request_id,
        user_agent=user_agent,
        ip=ip,
        extra={"is_mock": True},
    )
    raise EndpointInDevelopmentException(
        data=build_task_action(task_id=task_id, action="run"),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.post("/{task_id}/stop")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def stop_task(
    request: Request,
    task_id: int,
    user: User = Depends(current_user),
    audit_service: AuditService = Depends(get_audit_service),
    request_id: str = Depends(generate_request_id),
    _=Depends(require_permissions(TaskPermission.EXECUTE, bypass_superuser=True)),
):
    user_agent, ip = extract_client_info(request)
    await audit_service.log(
        action=AuditAction.TASK_STOP,
        result=AuditResult.SUCCESS,
        actor_id=user.id,
        resource_type="task",
        resource_id=str(task_id),
        request_id=request_id,
        user_agent=user_agent,
        ip=ip,
        extra={"is_mock": True},
    )
    raise EndpointInDevelopmentException(
        data=build_task_action(task_id=task_id, action="stop"),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.get("/{task_id}/executions")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_task_executions(
    task_id: int,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_task_executions(task_id=task_id, page=page, size=size),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.get("/{task_id}/executions/{execution_id}")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_task_execution_detail(
    task_id: int,
    execution_id: str,
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_task_execution_detail(task_id=task_id, execution_id=execution_id),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.post("/{task_id}/executions/{execution_id}/retry")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def retry_task_execution(
    task_id: int,
    execution_id: str,
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.EXECUTE, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_task_retry(task_id=task_id, execution_id=execution_id),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )
