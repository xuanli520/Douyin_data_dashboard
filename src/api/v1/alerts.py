from fastapi import APIRouter, Depends

from src.auth import current_user, User
from src.auth.rbac import require_permissions
from src.auth.permissions import AlertPermission
from src.core.endpoint_status import in_development

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
@in_development(
    mock_data={
        "alerts": [
            {
                "id": 1,
                "level": "P0",
                "title": "近1小时销售额跌幅 > 20%",
                "time": "10m ago",
                "status": "待处理",
            },
            {
                "id": 2,
                "level": "P1",
                "title": "直播间推流中断 (Room: 882)",
                "time": "32m ago",
                "status": "处理中",
            },
            {
                "id": 3,
                "level": "P2",
                "title": "库存同步延迟 (SKU: 9920)",
                "time": "2h ago",
                "status": "已忽略",
            },
        ],
        "summary": {"critical": 1, "warning": 5, "info": 12, "total": 18, "unread": 8},
    },
    expected_release="2026-03-01",
)
async def list_alerts(
    user: User = Depends(current_user),
    _=Depends(require_permissions(AlertPermission.VIEW, bypass_superuser=True)),
):
    pass
