from fastapi import APIRouter, Depends, Query

from src.auth import User, current_user
from src.auth.permissions import MetricPermission
from src.auth.rbac import require_permissions
from src.domains.experience.schemas import MetricDetailResponse
from src.domains.experience.services import (
    ExperienceQueryService,
    get_experience_service,
)
from src.exceptions import BusinessException
from src.responses.base import Response
from src.shared.errors import ErrorCode

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/{metric_type}")
async def get_metric_detail(
    metric_type: str,
    period: str = "30d",
    shop_id: int | None = Query(default=None),
    date_range: str | None = Query(default="30d"),
    service: ExperienceQueryService = Depends(get_experience_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(MetricPermission.VIEW, bypass_superuser=True)),
) -> Response[MetricDetailResponse]:
    if shop_id is None:
        raise BusinessException(ErrorCode.DATA_VALIDATION_FAILED, "shop_id is required")
    data = await service.get_metric_detail(
        shop_id=shop_id,
        metric_type=metric_type,
        period=period,
        date_range=date_range,
    )
    return Response.success(data=data)
