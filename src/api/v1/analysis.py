from fastapi import APIRouter, Depends

from src.auth import current_user, User
from src.auth.rbac import require_permissions
from src.auth.permissions import AnalysisPermission
from src.core.endpoint_status import in_development

router = APIRouter(prefix="/analysis", tags=["analysis"])


@in_development(
    mock_data={
        "analyses": [
            {
                "id": 1,
                "name": "Q1销售趋势分析",
                "type": "trend_analysis",
                "status": "completed",
                "created_at": "2026-01-10T10:00:00",
                "completed_at": "2026-01-10T10:05:00",
                "result_summary": "GMV环比增长12.5%，直播渠道贡献最大",
            }
        ],
        "total": 8,
        "recent_insights": [
            {
                "title": "转化率提升建议",
                "description": "建议优化详情页图片质量",
                "impact": "high",
                "confidence": 0.85,
            }
        ],
    },
    expected_release="2026-03-01",
)
@router.get("")
async def list_analyses(
    user: User = Depends(current_user),
    _=Depends(require_permissions(AnalysisPermission.VIEW, bypass_superuser=True)),
):
    pass
