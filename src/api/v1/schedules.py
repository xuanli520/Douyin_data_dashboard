from fastapi import APIRouter, Depends

from src.auth import current_user, User
from src.auth.rbac import require_permissions
from src.auth.permissions import SchedulePermission
from src.core.endpoint_status import in_development

router = APIRouter(prefix="/schedules", tags=["schedules"])


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
    expected_release="2026-03-01",
)
@router.get("")
async def list_schedules(
    user: User = Depends(current_user),
    _=Depends(require_permissions(SchedulePermission.VIEW, bypass_superuser=True)),
):
    pass
