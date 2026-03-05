from src.scrapers.shop_dashboard.parsers import (
    parse_comment_details,
    parse_core_scores,
    parse_violation_summary,
)


def test_parse_core_scores_maps_required_fields():
    payload = {
        "code": 0,
        "data": {
            "experience_score": {"value": "4.8"},
            "goods_score": {"value": 4.7},
            "logistics_score": {"value": "4.9"},
            "service_score": {"value": 4.6},
        },
    }

    result = parse_core_scores(payload)

    assert result["total_score"] == 4.8
    assert result["product_score"] == 4.7
    assert result["logistics_score"] == 4.9
    assert result["service_score"] == 4.6


def test_parse_comment_details_keeps_core_fields():
    payload = {
        "code": 0,
        "data": {
            "list": [
                {
                    "id": "c-1",
                    "product_id": "p-1",
                    "order_id": "o-1",
                    "content": "bad",
                    "shop_reply": "reply",
                    "comment_time": 1772674049,
                    "sku": "xl-red",
                }
            ]
        },
    }

    result = parse_comment_details(payload)

    assert result == [
        {
            "id": "c-1",
            "product_id": "p-1",
            "order_id": "o-1",
            "content": "bad",
            "shop_reply": "reply",
            "comment_time": 1772674049,
            "sku": "xl-red",
        }
    ]


def test_parse_violation_summary_aggregates_ticket_and_points():
    cash_payload = {"code": 0, "data": {"cash": {"deduct_amount": "123.4"}}}
    score_node_payload = {
        "code": 0,
        "data": {"score": {"a_level_point": 2, "b_level_point": 3}},
    }
    ticket_payload = {"code": 0, "data": {"total_count": 9}}

    result = parse_violation_summary(cash_payload, score_node_payload, ticket_payload)

    assert result["cash_deduct_amount"] == 123.4
    assert result["a_level_point"] == 2
    assert result["b_level_point"] == 3
    assert result["ticket_count"] == 9
