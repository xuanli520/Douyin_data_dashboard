from fastapi import APIRouter, Depends, Query

from src.api.v1.mock_data import build_metric_detail, normalize_dimension
from src.auth import User, current_user
from src.auth.permissions import MetricPermission
from src.auth.rbac import require_permissions
from src.core.endpoint_status import in_development
from src.exceptions import EndpointInDevelopmentException

router = APIRouter(prefix="/metrics", tags=["metrics"])
EXPECTED_RELEASE = "2026-04-30"


@router.get("/{metric_type}")
@in_development(
    mock_data={},
    expected_release=EXPECTED_RELEASE,
    prefer_real=True,
)
async def get_metric_detail(
    metric_type: str,
    period: str = "30d",
    shop_id: int = Query(default=1001),
    date_range: str | None = Query(default="30d"),
    user: User = Depends(current_user),
    _=Depends(require_permissions(MetricPermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_metric_detail(
            metric_type=normalize_dimension(metric_type),
            shop_id=shop_id,
            date_range=date_range,
            period=period,
        ),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )
