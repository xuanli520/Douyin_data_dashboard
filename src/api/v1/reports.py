from fastapi import APIRouter, Depends

from src.auth import current_user, User
from src.auth.rbac import require_permissions
from src.auth.permissions import ReportPermission
from src.core.endpoint_status import in_development

router = APIRouter(prefix="/reports", tags=["reports"])


@in_development(
    mock_data={
        "reports": [
            {
                "id": 1,
                "name": "月度销售报表",
                "type": "sales",
                "status": "generated",
                "created_at": "2026-01-01T00:00:00",
                "period": "2026-01",
            },
            {
                "id": 2,
                "name": "商品分析报表",
                "type": "product_analysis",
                "status": "generating",
                "created_at": "2026-01-15T10:00:00",
            },
        ],
        "total": 5,
    },
    expected_release="2026-03-01",
)
@router.get("")
async def list_reports(
    user: User = Depends(current_user),
    _=Depends(require_permissions(ReportPermission.VIEW, bypass_superuser=True)),
):
    pass
