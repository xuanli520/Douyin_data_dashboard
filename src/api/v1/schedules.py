from fastapi import APIRouter, Depends, HTTPException

from src.auth import current_user, User
from src.auth.permissions import SchedulePermission
from src.auth.rbac import require_permissions
from src.core.endpoint_status import in_development
from src.domains.collection_job.schemas import (
    CollectionJobResponse,
    CollectionJobUpdate,
)
from src.domains.collection_job.services import (
    CollectionJobService,
    get_collection_job_service,
)
from src.responses.base import Response

router = APIRouter(prefix="/schedules", tags=["schedules"])
EXPECTED_RELEASE = "2026-04-30"


@router.get("")
@in_development(
    mock_data={
        "schedules": [
            {
                "id": 1,
                "name": "每日GMV统计",
                "cron": "0 9 * * *",
                "timezone": "Asia/Shanghai",
                "status": "active",
                "last_run": "2026-01-15T09:00:00",
                "next_run": "2026-01-16T09:00:00",
            },
            {
                "id": 2,
                "name": "商品库存同步",
                "cron": "0 */4 * * *",
                "timezone": "Asia/Shanghai",
                "status": "paused",
                "last_run": "2026-01-15T08:00:00",
                "next_run": None,
            },
        ],
        "total": 3,
    },
    expected_release=EXPECTED_RELEASE,
)
async def list_schedules(
    user: User = Depends(current_user),
    _=Depends(require_permissions(SchedulePermission.VIEW, bypass_superuser=True)),
):
    pass


@router.put("/{schedule_id}", response_model=Response[CollectionJobResponse])
async def update_schedule(
    schedule_id: int,
    payload: CollectionJobUpdate,
    service: CollectionJobService = Depends(get_collection_job_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(SchedulePermission.UPDATE, bypass_superuser=True)),
) -> Response[CollectionJobResponse]:
    updated = await service.update_job(schedule_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return Response.success(data=updated)


@router.delete("/{schedule_id}", response_model=Response[None])
async def delete_schedule(
    schedule_id: int,
    service: CollectionJobService = Depends(get_collection_job_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(SchedulePermission.DELETE, bypass_superuser=True)),
) -> Response[None]:
    deleted = await service.delete_job(schedule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return Response.success()
