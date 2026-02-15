from typing import Any

from fastapi import APIRouter, Depends

from src.auth import current_user, User
from src.auth.rbac import require_permissions
from src.auth.permissions import TaskPermission
from src.core.endpoint_status import in_development

router = APIRouter(prefix="/tasks", tags=["task"])


@router.get("")
@in_development(
    mock_data=lambda: [
        {
            "id": 1,
            "name": "订单采集任务",
            "task_type": "order_collection",
            "status": "running",
            "progress": 45,
            "created_at": "2026-01-15T10:00:00",
        },
        {
            "id": 2,
            "name": "商品数据同步",
            "task_type": "product_sync",
            "status": "completed",
            "progress": 100,
            "created_at": "2026-01-14T08:00:00",
        },
    ],
    expected_release="2026-03-01",
)
async def list_tasks(
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.VIEW, bypass_superuser=True)),
):
    pass


@router.post("")
@in_development(
    mock_data={
        "id": 3,
        "name": "新建任务",
        "task_type": "order_collection",
        "status": "pending",
        "created_at": "2026-01-15T12:00:00",
    },
    expected_release="2026-03-01",
)
async def create_task(
    data: dict[str, Any],
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.CREATE, bypass_superuser=True)),
):
    pass


@router.post("/{task_id}/run")
@in_development(
    mock_data={
        "execution_id": "exec_123",
        "status": "running",
        "started_at": "2026-01-15T12:00:00",
    },
    expected_release="2026-03-01",
)
async def run_task(
    task_id: int,
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.EXECUTE, bypass_superuser=True)),
):
    pass


@router.get("/{task_id}/executions")
@in_development(
    mock_data=lambda: [
        {
            "execution_id": "exec_001",
            "task_id": 1,
            "status": "completed",
            "started_at": "2026-01-15T10:00:00",
            "completed_at": "2026-01-15T10:05:00",
            "records_processed": 1256,
        }
    ],
    expected_release="2026-03-01",
)
async def get_task_executions(
    task_id: int,
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.VIEW, bypass_superuser=True)),
):
    pass
