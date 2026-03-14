from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from src.audit import AuditService, get_audit_service
from src.audit.dependencies import generate_request_id
from src.audit.schemas import AuditAction, AuditResult
from src.audit.service import extract_client_info
from src.auth import User, current_user
from src.auth.permissions import TaskPermission
from src.auth.rbac import require_permissions
from src.domains.task.enums import TaskDefinitionStatus, TaskType
from src.domains.task.schemas import (
    TaskDefinitionCreate,
    TaskDefinitionResponse,
    TaskExecutionResponse,
    TaskRunRequest,
)
from src.domains.task.services import TaskService, get_task_service
from src.exceptions import TaskNotFoundException
from src.responses.base import Response

router = APIRouter(prefix="/tasks", tags=["task"])


def _pagination_meta(page: int, size: int, total: int) -> dict[str, int | bool]:
    pages = (total + size - 1) // size if size > 0 else 0
    return {
        "page": page,
        "size": size,
        "total": total,
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }


def _task_data(task: Any) -> dict[str, Any]:
    return TaskDefinitionResponse.model_validate(task).model_dump(mode="json")


def _execution_data(execution: Any) -> dict[str, Any]:
    return TaskExecutionResponse.model_validate(execution).model_dump(mode="json")


async def _log_task_audit(
    request: Request,
    audit_service: AuditService,
    request_id: str,
    *,
    user: User,
    action: AuditAction,
    resource_id: str,
    extra: dict[str, Any] | None = None,
) -> None:
    user_agent, ip = extract_client_info(request)
    await audit_service.log(
        action=action,
        result=AuditResult.SUCCESS,
        actor_id=user.id,
        resource_type="task",
        resource_id=resource_id,
        request_id=request_id,
        user_agent=user_agent,
        ip=ip,
        extra=extra,
    )


async def _get_task_or_raise(service: TaskService, task_id: int) -> Any:
    task = await service.get_task(task_id)
    if task is None:
        raise TaskNotFoundException(task_id=str(task_id))
    return task


@router.get("", response_model=Response[dict[str, Any]])
async def list_tasks(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    status: TaskDefinitionStatus | None = Query(default=None),
    task_type: TaskType | None = Query(default=None),
    service: TaskService = Depends(get_task_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.VIEW, bypass_superuser=True)),
) -> Response[dict[str, Any]]:
    _ = user
    tasks, total = await service.list_tasks(
        page=page,
        size=size,
        status=status,
        task_type=task_type,
    )
    return Response.success(
        data={
            "items": [_task_data(task) for task in tasks],
            "meta": _pagination_meta(page=page, size=size, total=total),
        }
    )


@router.post("", response_model=Response[dict[str, Any]])
async def create_task(
    request: Request,
    payload: TaskDefinitionCreate,
    service: TaskService = Depends(get_task_service),
    user: User = Depends(current_user),
    audit_service: AuditService = Depends(get_audit_service),
    request_id: str = Depends(generate_request_id),
    _=Depends(require_permissions(TaskPermission.CREATE, bypass_superuser=True)),
) -> Response[dict[str, Any]]:
    task = await service.create_task(payload, created_by_id=user.id)
    await _log_task_audit(
        request=request,
        audit_service=audit_service,
        request_id=request_id,
        user=user,
        action=AuditAction.TASK_CREATE,
        resource_id=str(task.id if task.id is not None else 0),
        extra={"task_type": task.task_type.value, "name": task.name},
    )
    return Response.success(data=_task_data(task))


@router.get("/{task_id}", response_model=Response[dict[str, Any]])
async def get_task(
    task_id: int,
    service: TaskService = Depends(get_task_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.VIEW, bypass_superuser=True)),
) -> Response[dict[str, Any]]:
    _ = user
    task = await _get_task_or_raise(service, task_id)
    return Response.success(data=_task_data(task))


@router.post("/{task_id}/run", response_model=Response[dict[str, Any]])
async def run_task(
    request: Request,
    task_id: int,
    payload: TaskRunRequest | None = None,
    service: TaskService = Depends(get_task_service),
    user: User = Depends(current_user),
    audit_service: AuditService = Depends(get_audit_service),
    request_id: str = Depends(generate_request_id),
    _=Depends(require_permissions(TaskPermission.EXECUTE, bypass_superuser=True)),
) -> Response[dict[str, Any]]:
    await _get_task_or_raise(service, task_id)
    execution = await service.run_task(
        task_id=task_id,
        payload=payload.payload if payload else {},
        triggered_by=user.id,
    )
    await _log_task_audit(
        request=request,
        audit_service=audit_service,
        request_id=request_id,
        user=user,
        action=AuditAction.TASK_RUN,
        resource_id=str(task_id),
        extra={
            "execution_id": execution.id if execution.id is not None else 0,
            "queue_task_id": execution.queue_task_id,
            "trigger_mode": execution.trigger_mode.value,
        },
    )
    return Response.success(data=_execution_data(execution))


@router.post("/{task_id}/cancel", response_model=Response[dict[str, Any]])
async def cancel_task(
    request: Request,
    task_id: int,
    service: TaskService = Depends(get_task_service),
    user: User = Depends(current_user),
    audit_service: AuditService = Depends(get_audit_service),
    request_id: str = Depends(generate_request_id),
    _=Depends(require_permissions(TaskPermission.CANCEL, bypass_superuser=True)),
) -> Response[dict[str, Any]]:
    task = await _get_task_or_raise(service, task_id)
    task = await service.cancel_task(task, changed_by_id=user.id)
    await _log_task_audit(
        request=request,
        audit_service=audit_service,
        request_id=request_id,
        user=user,
        action=AuditAction.TASK_STOP,
        resource_id=str(task_id),
        extra={"status": task.status.value},
    )
    return Response.success(data=_task_data(task))


@router.get("/{task_id}/executions", response_model=Response[dict[str, Any]])
async def list_task_executions(
    task_id: int,
    service: TaskService = Depends(get_task_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.VIEW, bypass_superuser=True)),
) -> Response[dict[str, Any]]:
    _ = user
    await _get_task_or_raise(service, task_id)
    executions = await service.list_executions(task_id)
    return Response.success(
        data={
            "task_id": task_id,
            "items": [_execution_data(execution) for execution in executions],
        }
    )
