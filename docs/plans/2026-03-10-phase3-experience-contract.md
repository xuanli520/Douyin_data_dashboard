# Phase 3 Experience API Contract Freeze (M1)

## 1) Metric Mapping Table

| dimension | metric_key | source_field | formula | unit | deduct_points |
| --- | --- | --- | --- | --- | --- |
| product | product_quality_score | raw.product.quality_score | weighted_quality_feedback | pt | false |
| product | product_return_rate | raw.product.return_rate | returns/orders*100 | % | false |
| product | product_negative_review_rate | raw.product.negative_review_rate | negative_reviews/reviews*100 | % | false |
| logistics | pickup_sla | raw.logistics.pickup_sla | pickup_in_24h_orders/fulfilled_orders*100 | % | false |
| logistics | delivery_sla | raw.logistics.delivery_sla | delivery_in_72h_orders/fulfilled_orders*100 | % | false |
| logistics | logistics_return_rate | raw.logistics.damage_return_rate | damage_returns/delivered_orders*100 | % | false |
| service | response_latency | raw.service.first_response_seconds | avg(first_response_seconds) | s | false |
| service | after_sales_resolution_rate | raw.service.after_sales_resolution_rate | resolved_after_sales/after_sales_total*100 | % | false |
| service | service_satisfaction | raw.service.satisfaction_score | positive_service_reviews/service_reviews*100 | % | false |
| risk | fake_transaction | raw.risk.fake_transaction_cases | risk_penalty(fake_transaction_cases) | pt | true |
| risk | policy_violation | raw.risk.policy_violation_cases | risk_penalty(policy_violation_cases) | pt | true |
| risk | customer_complaint_penalty | raw.risk.customer_complaint_cases | risk_penalty(customer_complaint_cases) | pt | true |

## 2) Frozen Response Structures

- `GET /api/v1/experience/overview`: `{shop_id,date_range,overall_score,dimensions,alerts}`
- `GET /api/v1/experience/trend`: `{shop_id,dimension,date_range,trend}`
- `GET /api/v1/experience/issues`: `{items,meta}`
- `GET /api/v1/experience/drilldown/{dimension}`:
  `{shop_id,dimension,date_range,category_score,sub_metrics,score_ranges,formula,trend,issues}`
- `GET /api/v1/metrics/{metric_type}`:
  `{shop_id,metric_type,period,date_range,category_score,sub_metrics,score_ranges,formula,trend}`

All endpoints return unified envelope: `code=200,msg=success,data=<payload>`.

## 3) expected_release Policy

- Phase 3 real endpoints (`experience/*`, `metrics/{metric_type}`, `dashboard/overview`, `dashboard/kpis`) remove:
  - `@in_development(...)`
  - `EndpointInDevelopmentException`
  - `expected_release` in payload
- Keep existing RBAC dependency chain unchanged.

## 4) FE/BE Joint Review Checklist

- No unresolved fields in the payloads above.
- No alias mismatch for dimension and metric keys.
- FE no longer parses `data.mock` / `data.expected_release` for the migrated endpoints.
