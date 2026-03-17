from src.domains.experience.presentation_mapper import (
    build_dashboard_kpis,
    build_dashboard_overview,
    build_issues,
    build_metric_detail,
    build_overview,
)
from src.domains.experience.schemas import DIMENSION_WEIGHTS


def _materials() -> list[dict]:
    return [
        {
            "shop_id": "1001",
            "metric_date": "2026-03-01",
            "source": "seed",
            "total_score": 4.2,
            "product_score": 4.4,
            "logistics_score": 4.1,
            "service_score": 4.0,
            "bad_behavior_score": 0.6,
            "violations": [],
            "cold_metrics": [{"reason": "cold fallback reason"}],
        },
        {
            "shop_id": "1001",
            "metric_date": "2026-03-02",
            "source": "seed",
            "total_score": 4.5,
            "product_score": 4.6,
            "logistics_score": 4.4,
            "service_score": 4.5,
            "bad_behavior_score": 0.8,
            "violations": [
                {
                    "id": "issue-1",
                    "type": "product",
                    "description": "product issue",
                    "score": 6,
                }
            ],
            "cold_metrics": [],
        },
    ]


def test_overview_dimension_scores_should_map_from_shop_dashboard_scores():
    payload = build_overview(
        shop_id=1001,
        date_range="30d",
        materials=_materials(),
        dimension_weights=DIMENSION_WEIGHTS,
    )

    dimensions = {item["dimension"]: item["score"] for item in payload["dimensions"]}
    assert payload["shop_id"] == 1001
    assert payload["overall_score"] == 90.2
    assert dimensions["product"] == 92.0
    assert dimensions["logistics"] == 88.0
    assert dimensions["service"] == 90.0
    assert dimensions["risk"] == 84.0


def test_issues_should_use_violations_first_then_cold_reason_fallback():
    payload = build_issues(
        shop_id=1001,
        date_range="30d",
        materials=_materials(),
        dimension="all",
        status="all",
        page=1,
        size=20,
    )

    ids = {item["id"] for item in payload["items"]}
    assert "issue-1" in ids
    assert "cold-2026-03-01-1" in ids
    assert payload["meta"]["total"] == 2


def test_metric_detail_should_keep_contract_shape():
    payload = build_metric_detail(
        shop_id=1001,
        metric_type="product",
        period="30d",
        date_range="30d",
        materials=_materials(),
    )

    assert payload["metric_type"] == "product"
    assert isinstance(payload["sub_metrics"], list)
    assert len(payload["sub_metrics"]) == 3
    assert {"id", "title", "score", "weight", "value", "desc"} <= set(
        payload["sub_metrics"][0].keys()
    )
    assert isinstance(payload["trend"], list)


def test_dashboard_kpis_should_keep_existing_structure():
    overview = build_overview(
        shop_id=1001,
        date_range="30d",
        materials=_materials(),
        dimension_weights=DIMENSION_WEIGHTS,
    )
    dashboard_overview = build_dashboard_overview(
        shop_id=1001,
        date_range="30d",
        materials=_materials(),
        overview_payload=overview,
    )
    payload = build_dashboard_kpis(
        shop_id=1001,
        date_range="30d",
        materials=_materials(),
        overview_payload=dashboard_overview,
    )

    assert payload["shop_id"] == 1001
    assert [item["id"] for item in payload["kpis"]] == [
        "orders",
        "gmv",
        "refund_rate",
    ]
    assert {"date", "orders", "gmv"} <= set(payload["trend"][0].keys())
