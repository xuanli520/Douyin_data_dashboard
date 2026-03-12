# Phase 3 Experience Real API Examples

Last updated: 2026-03-12

## Scope

The following endpoints are now real-data endpoints in Phase 3:

- `GET /api/v1/experience/overview`
- `GET /api/v1/experience/trend`
- `GET /api/v1/experience/issues`
- `GET /api/v1/experience/drilldown/{dimension}`
- `GET /api/v1/metrics/{metric_type}`
- `GET /api/v1/dashboard/overview`
- `GET /api/v1/dashboard/kpis`

All success responses use the same envelope:

```json
{
  "code": 200,
  "msg": "success",
  "data": {}
}
```

## Four-Dimension Metric Examples

### 1) Product

Request:

```http
GET /api/v1/metrics/product?shop_id=1001&date_range=30d&period=30d
```

Response example:

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "shop_id": 1001,
    "metric_type": "product",
    "period": "30d",
    "date_range": "30d",
    "category_score": 92.0,
    "sub_metrics": [
      {"id": "product_quality_score", "score": 93.0, "value": "93.0pt"},
      {"id": "product_return_rate", "score": 89.0, "value": "1.8%"},
      {"id": "product_negative_review_rate", "score": 87.0, "value": "2.4%"}
    ],
    "trend": [{"date": "2026-03-03", "value": 92.0}]
  }
}
```

### 2) Logistics

Request:

```http
GET /api/v1/metrics/logistics?shop_id=1001&date_range=30d&period=30d
```

Response example:

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "shop_id": 1001,
    "metric_type": "logistics",
    "period": "30d",
    "date_range": "30d",
    "category_score": 89.0,
    "sub_metrics": [
      {"id": "pickup_sla", "score": 90.0, "value": "95.0%"},
      {"id": "delivery_sla", "score": 88.0, "value": "93.0%"},
      {"id": "logistics_return_rate", "score": 87.0, "value": "1.2%"}
    ],
    "trend": [{"date": "2026-03-03", "value": 89.0}]
  }
}
```

### 3) Service

Request:

```http
GET /api/v1/metrics/service?shop_id=1001&date_range=30d&period=30d
```

Response example:

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "shop_id": 1001,
    "metric_type": "service",
    "period": "30d",
    "date_range": "30d",
    "category_score": 88.0,
    "sub_metrics": [
      {"id": "response_latency", "score": 86.0, "value": "22.0s"},
      {"id": "after_sales_resolution_rate", "score": 89.0, "value": "92.0%"},
      {"id": "service_satisfaction", "score": 90.0, "value": "94.0%"}
    ],
    "trend": [{"date": "2026-03-03", "value": 88.0}]
  }
}
```

### 4) Risk

Request:

```http
GET /api/v1/metrics/risk?shop_id=1001&date_range=30d&period=30d
```

Response example:

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "shop_id": 1001,
    "metric_type": "risk",
    "period": "30d",
    "date_range": "30d",
    "category_score": 79.0,
    "sub_metrics": [
      {
        "id": "fake_transaction",
        "score": 78.0,
        "deduct_points": 22.0,
        "impact_score": 14.3,
        "status": "processing"
      }
    ],
    "trend": [{"date": "2026-03-03", "value": 79.0}]
  }
}
```

## Integration Notes

- Use `docs/phase3-experience-seed.sql` to initialize integration data.
- `issues` endpoint supports `dimension`, `status`, `date_range`, `page`, `size`.
- Cache strategy:
  - metrics: 1 hour
  - dashboard: 30 minutes
  - issues: 5 minutes
- Collection write success triggers `shop_id + metric_date` precise cache invalidation.
