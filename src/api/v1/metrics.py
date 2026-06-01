from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from src.auth import User, current_user
from src.auth.permissions import MetricPermission
from src.auth.permissions import ShopPermission
from src.auth.rbac import require_permissions
from src.domains.agent_result.services import (
    AgentResultService,
    get_agent_result_service,
)
from src.domains.experience.schemas import MetricDetailResponse
from src.domains.experience.services import (
    ExperienceQueryService,
    get_experience_service,
)
from src.responses.base import Response

router = APIRouter(prefix="/metrics", tags=["metrics"])

METRIC_RECIPE_KEY_MAP = {
    "product": "experience_score_product_detail",
    "logistics": "experience_score_logistics_detail",
    "service": "experience_score_service_detail",
    "risk": "experience_score_bad_behavior_detail",
}


@router.get("/{metric_type}/download", response_class=StreamingResponse)
async def download_metric_detail_csv(
    metric_type: str,
    shop_id: int = Query(...),
    date_from: date = Query(...),
    date_to: date = Query(...),
    _user: User = Depends(current_user),
    _=Depends(require_permissions(ShopPermission.VIEW, bypass_superuser=True)),
    service: AgentResultService = Depends(get_agent_result_service),
) -> StreamingResponse:
    recipe_key = METRIC_RECIPE_KEY_MAP.get(metric_type)
    if recipe_key is None:
        recipe_key = metric_type
    csv_content, filename = await service.build_csv_by_recipe_key(
        namespace="douyin_shop_dashboard",
        resource_key=str(shop_id),
        recipe_key=recipe_key,
        date_from=date_from,
        date_to=date_to,
    )
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{metric_type}")
async def get_metric_detail(
    metric_type: str,
    period: str = "30d",
    shop_id: int = Query(default=1001),
    date_range: str | None = Query(default="30d"),
    service: ExperienceQueryService = Depends(get_experience_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(MetricPermission.VIEW, bypass_superuser=True)),
) -> Response[MetricDetailResponse]:
    data = await service.get_metric_detail(
        shop_id=shop_id,
        metric_type=metric_type,
        period=period,
        date_range=date_range,
    )
    return Response.success(data=data)
