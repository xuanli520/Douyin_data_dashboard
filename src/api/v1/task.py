from typing import Any

from fastapi import APIRouter, Depends

from src.auth import current_user, User
from src.auth.rbac import require_permissions
from src.auth.permissions import TaskPermission
from src.responses.base import Response

router = APIRouter(prefix="/tasks", tags=["task"])


@router.get("", response_model=Response[list[dict[str, Any]]])
async def list_tasks(
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.VIEW, bypass_superuser=True)),
) -> Response[list[dict[str, Any]]]:
    return Response.success(data=[])


@router.post("", response_model=Response[dict[str, Any]])
async def create_task(
    data: dict[str, Any],
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.CREATE, bypass_superuser=True)),
) -> Response[dict[str, Any]]:
    return Response.success(
        data={
            "id": 1,
            "name": data.get("name", "Test Task"),
            "task_type": data.get("task_type", "order_collection"),
            "data_source_id": data.get("data_source_id", 1),
            "schedule": data.get("schedule"),
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        }
    )


@router.post("/{task_id}/run", response_model=Response[dict[str, Any]])
async def run_task(
    task_id: int,
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.EXECUTE, bypass_superuser=True)),
) -> Response[dict[str, Any]]:
    return Response.success(data={"execution_id": "exec_123", "status": "running"})


@router.get("/{task_id}/executions", response_model=Response[list[dict[str, Any]]])
async def get_task_executions(
    task_id: int,
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.VIEW, bypass_superuser=True)),
) -> Response[list[dict[str, Any]]]:
    return Response.success(data=[])
