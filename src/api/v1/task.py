from __future__ import annotations

from datetime import date as date_type
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.audit import AuditService, get_audit_service
from src.audit.dependencies import generate_request_id
from src.audit.schemas import AuditAction, AuditResult
from src.audit.service import extract_client_info
from src.auth import User, current_user
from src.auth.permissions import TaskPermission
from src.auth.rbac import require_permissions
from src.tasks.collection.douyin_orders import sync_orders
from src.tasks.collection.douyin_products import sync_products
from src.tasks.etl.orders import process_orders
from src.tasks.etl.products import process_products

router = APIRouter(prefix="/tasks", tags=["task"])


class CollectionTriggerPayload(BaseModel):
    shop_id: str = Field(min_length=1)
    date: date_type


class EtlTriggerPayload(BaseModel):
    batch_date: date_type


def _audit_extra(
    queue_name: str, payload: dict[str, Any], task_id: str
) -> dict[str, Any]:
    return {"queue_name": queue_name, "payload": payload, "task_id": task_id}


async def _log_task_trigger(
    request: Request,
    audit_service: AuditService,
    request_id: str,
    user: User,
    queue_name: str,
    payload: dict[str, Any],
    task_id: str,
) -> None:
    user_agent, ip = extract_client_info(request)
    await audit_service.log(
        action=AuditAction.TASK_RUN,
        result=AuditResult.SUCCESS,
        actor_id=user.id,
        resource_type="task",
        resource_id=task_id,
        request_id=request_id,
        user_agent=user_agent,
        ip=ip,
        extra=_audit_extra(queue_name=queue_name, payload=payload, task_id=task_id),
    )


def _trigger_result(async_result: Any, queue_name: str, user_id: int) -> dict[str, Any]:
    task_id = getattr(async_result, "task_id", None)
    if not task_id:
        raise HTTPException(status_code=500, detail="Task push failed: missing task_id")
    return {"task_id": str(task_id), "queue_name": queue_name, "triggered_by": user_id}


@router.post("/collection/orders/trigger")
async def trigger_collection_orders(
    request: Request,
    payload: CollectionTriggerPayload,
    user: User = Depends(current_user),
    audit_service: AuditService = Depends(get_audit_service),
    request_id: str = Depends(generate_request_id),
    _=Depends(require_permissions(TaskPermission.EXECUTE, bypass_superuser=True)),
) -> dict[str, Any]:
    push_result = sync_orders.push(
        shop_id=payload.shop_id,
        date=payload.date.isoformat(),
        triggered_by=user.id,
    )
    response_data = _trigger_result(push_result, "collection_orders", user.id)
    await _log_task_trigger(
        request=request,
        audit_service=audit_service,
        request_id=request_id,
        user=user,
        queue_name="collection_orders",
        payload=payload.model_dump(mode="json"),
        task_id=response_data["task_id"],
    )
    return response_data


@router.post("/collection/products/trigger")
async def trigger_collection_products(
    request: Request,
    payload: CollectionTriggerPayload,
    user: User = Depends(current_user),
    audit_service: AuditService = Depends(get_audit_service),
    request_id: str = Depends(generate_request_id),
    _=Depends(require_permissions(TaskPermission.EXECUTE, bypass_superuser=True)),
) -> dict[str, Any]:
    push_result = sync_products.push(
        shop_id=payload.shop_id,
        date=payload.date.isoformat(),
        triggered_by=user.id,
    )
    response_data = _trigger_result(push_result, "collection_products", user.id)
    await _log_task_trigger(
        request=request,
        audit_service=audit_service,
        request_id=request_id,
        user=user,
        queue_name="collection_products",
        payload=payload.model_dump(mode="json"),
        task_id=response_data["task_id"],
    )
    return response_data


@router.post("/etl/orders/trigger")
async def trigger_etl_orders(
    request: Request,
    payload: EtlTriggerPayload,
    user: User = Depends(current_user),
    audit_service: AuditService = Depends(get_audit_service),
    request_id: str = Depends(generate_request_id),
    _=Depends(require_permissions(TaskPermission.EXECUTE, bypass_superuser=True)),
) -> dict[str, Any]:
    push_result = process_orders.push(
        batch_date=payload.batch_date.isoformat(),
        triggered_by=user.id,
    )
    response_data = _trigger_result(push_result, "etl_orders", user.id)
    await _log_task_trigger(
        request=request,
        audit_service=audit_service,
        request_id=request_id,
        user=user,
        queue_name="etl_orders",
        payload=payload.model_dump(mode="json"),
        task_id=response_data["task_id"],
    )
    return response_data


@router.post("/etl/products/trigger")
async def trigger_etl_products(
    request: Request,
    payload: EtlTriggerPayload,
    user: User = Depends(current_user),
    audit_service: AuditService = Depends(get_audit_service),
    request_id: str = Depends(generate_request_id),
    _=Depends(require_permissions(TaskPermission.EXECUTE, bypass_superuser=True)),
) -> dict[str, Any]:
    push_result = process_products.push(
        batch_date=payload.batch_date.isoformat(),
        triggered_by=user.id,
    )
    response_data = _trigger_result(push_result, "etl_products", user.id)
    await _log_task_trigger(
        request=request,
        audit_service=audit_service,
        request_id=request_id,
        user=user,
        queue_name="etl_products",
        payload=payload.model_dump(mode="json"),
        task_id=response_data["task_id"],
    )
    return response_data


# Backward compatible endpoints kept during migration window.
@router.get("")
async def list_tasks(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.VIEW, bypass_superuser=True)),
) -> dict[str, Any]:
    _ = user
    return {
        "items": [],
        "meta": {
            "page": page,
            "size": size,
            "total": 0,
            "pages": 0,
            "has_next": False,
            "has_prev": page > 1,
        },
    }


class LegacyTaskCreatePayload(BaseModel):
    name: str
    task_type: str


@router.post("")
async def create_task(
    request: Request,
    payload: LegacyTaskCreatePayload,
    user: User = Depends(current_user),
    audit_service: AuditService = Depends(get_audit_service),
    request_id: str = Depends(generate_request_id),
    _=Depends(require_permissions(TaskPermission.CREATE, bypass_superuser=True)),
) -> dict[str, Any]:
    push_result = sync_orders.push(
        shop_id=payload.name,
        date=date_type.today().isoformat(),
        triggered_by=user.id,
    )
    response_data = _trigger_result(push_result, "collection_orders", user.id)
    await _log_task_trigger(
        request=request,
        audit_service=audit_service,
        request_id=request_id,
        user=user,
        queue_name="collection_orders",
        payload=payload.model_dump(mode="json"),
        task_id=response_data["task_id"],
    )
    return response_data


@router.post("/{task_id}/run")
async def run_task(
    request: Request,
    task_id: int,
    user: User = Depends(current_user),
    audit_service: AuditService = Depends(get_audit_service),
    request_id: str = Depends(generate_request_id),
    _=Depends(require_permissions(TaskPermission.EXECUTE, bypass_superuser=True)),
) -> dict[str, Any]:
    push_result = sync_orders.push(
        shop_id=f"task-{task_id}",
        date=date_type.today().isoformat(),
        triggered_by=user.id,
    )
    response_data = _trigger_result(push_result, "collection_orders", user.id)
    await _log_task_trigger(
        request=request,
        audit_service=audit_service,
        request_id=request_id,
        user=user,
        queue_name="collection_orders",
        payload={"legacy_task_id": task_id},
        task_id=response_data["task_id"],
    )
    return response_data


@router.get("/{task_id}/executions")
async def get_task_executions(
    task_id: int,
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.VIEW, bypass_superuser=True)),
) -> dict[str, Any]:
    _ = user
    return {"task_id": task_id, "items": []}
