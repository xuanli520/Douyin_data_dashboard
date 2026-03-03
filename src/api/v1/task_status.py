from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, Request
from redis import Redis
from redis.exceptions import RedisError

from src.audit import AuditService, get_audit_service
from src.audit.dependencies import generate_request_id
from src.audit.schemas import AuditAction, AuditResult
from src.audit.service import extract_client_info
from src.auth import User, current_user
from src.auth.permissions import TaskPermission
from src.auth.rbac import require_permissions
from src.config import get_settings
from src.exceptions import TaskNotFoundException, TaskStatusBackendUnavailableException

router = APIRouter(prefix="/task-status", tags=["task-status"])


@lru_cache(maxsize=1)
def _get_redis_client() -> Redis:
    settings = get_settings()
    cache_settings = settings.cache
    status_db = settings.funboost.filter_and_rpc_result_redis_db
    if cache_settings.password:
        url = (
            f"redis://:{cache_settings.password}@"
            f"{cache_settings.host}:{cache_settings.port}/{status_db}"
        )
    else:
        url = f"redis://{cache_settings.host}:{cache_settings.port}/{status_db}"
    return Redis.from_url(url, decode_responses=True)


@router.get("/{task_id}")
async def get_task_status(
    request: Request,
    task_id: str,
    user: User = Depends(current_user),
    audit_service: AuditService = Depends(get_audit_service),
    request_id: str = Depends(generate_request_id),
    _=Depends(require_permissions(TaskPermission.VIEW, bypass_superuser=True)),
) -> dict[str, Any]:
    redis_client = _get_redis_client()
    key = f"douyin:task:status:{task_id}"
    try:
        data = redis_client.hgetall(key)
    except RedisError as exc:
        raise TaskStatusBackendUnavailableException() from exc
    except Exception as exc:
        raise TaskStatusBackendUnavailableException() from exc

    if not data:
        raise TaskNotFoundException(task_id=task_id)

    user_agent, ip = extract_client_info(request)
    await audit_service.log(
        action=AuditAction.PROTECTED_RESOURCE_ACCESS,
        result=AuditResult.SUCCESS,
        actor_id=user.id,
        resource_type="task_status",
        resource_id=task_id,
        request_id=request_id,
        user_agent=user_agent,
        ip=ip,
        extra={"status_key": key},
    )
    return {"task_id": task_id, "status": data}
