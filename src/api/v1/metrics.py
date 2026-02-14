from fastapi import APIRouter, Depends

from src.auth import current_user, User
from src.auth.rbac import require_permissions
from src.auth.permissions import MetricPermission
from src.core.endpoint_status import in_development

router = APIRouter(prefix="/metrics", tags=["metrics"])


MOCK_METRICS = {
    "product": {
        "id": "product",
        "score": 100,
        "themeKey": "product",
        "subMetrics": [
            {
                "id": "p1",
                "title": "商品综合评分",
                "score": 100,
                "weight": "90%",
                "value": "4.8702",
                "unit": "分",
                "desc": "近30天消费者评价加权平均分",
            },
            {
                "id": "p2",
                "title": "商品品质退货率",
                "score": 100,
                "weight": "10%",
                "value": "0.195%",
                "unit": "",
                "desc": "品质原因退货占比",
            },
        ],
    },
    "logistics": {
        "id": "logistics",
        "score": 100,
        "themeKey": "logistics",
        "subMetrics": [
            {
                "id": "l1",
                "title": "揽收时效达成率",
                "score": 100,
                "weight": "15%",
                "value": "100%",
                "unit": "",
            },
            {
                "id": "l2",
                "title": "运单配送时效达成率",
                "score": 100,
                "weight": "70%",
                "value": "95.79%",
                "unit": "",
            },
            {
                "id": "l3",
                "title": "发货物流品退率",
                "score": 100,
                "weight": "15%",
                "value": "0.02%",
                "unit": "",
            },
        ],
    },
    "service": {
        "id": "service",
        "score": 100,
        "themeKey": "service",
        "subMetrics": [
            {
                "id": "s1",
                "title": "飞鸽平均响应时长",
                "score": 100,
                "weight": "70%",
                "value": "10.6s",
                "unit": "",
            },
            {
                "id": "s2",
                "title": "售后处理时长达成率",
                "score": 100,
                "weight": "30%",
                "value": "95.6%",
                "unit": "",
            },
        ],
    },
    "risk": {
        "id": "risk",
        "score": 0,
        "themeKey": "risk",
        "isDeduction": True,
        "subMetrics": [
            {
                "id": "r1",
                "title": "虚假交易刷体验分扣分",
                "score": 0,
                "value": "0分",
                "unit": "",
                "isRisk": True,
            },
            {
                "id": "r2",
                "title": "影响消费者体验扣分",
                "score": 0,
                "value": "0分",
                "unit": "",
                "isRisk": True,
            },
        ],
    },
}


@in_development(
    mock_data=lambda: MOCK_METRICS["product"],
    expected_release="2026-03-01",
)
@router.get("/{metric_type}")
async def get_metric_detail(
    metric_type: str,
    period: str = "30d",
    user: User = Depends(current_user),
    _=Depends(require_permissions(MetricPermission.VIEW, bypass_superuser=True)),
):
    pass
