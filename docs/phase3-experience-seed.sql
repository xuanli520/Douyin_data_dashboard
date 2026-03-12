-- Phase 3 experience integration seed data
-- Updated: 2026-03-12
-- Usage:
--   psql "$DATABASE_URL" -f docs/phase3-experience-seed.sql

BEGIN;

DELETE FROM experience_issue_daily WHERE shop_id = '1001';
DELETE FROM experience_metric_daily WHERE shop_id = '1001';

-- dimension_score rows (trend + overview source)
INSERT INTO experience_metric_daily (
    shop_id,
    metric_date,
    dimension,
    metric_key,
    metric_score,
    metric_value,
    metric_unit,
    source_field,
    formula_expr,
    is_penalty,
    deduct_points,
    source,
    extra
)
VALUES
    ('1001', '2026-03-01', 'product',   'dimension_score', 90.0, 90.0, 'pt', 'raw.product.score',   'normalized_dimension_score', FALSE, 0.0,  'seed', '{}'),
    ('1001', '2026-03-01', 'logistics', 'dimension_score', 88.0, 88.0, 'pt', 'raw.logistics.score', 'normalized_dimension_score', FALSE, 0.0,  'seed', '{}'),
    ('1001', '2026-03-01', 'service',   'dimension_score', 86.0, 86.0, 'pt', 'raw.service.score',   'normalized_dimension_score', FALSE, 0.0,  'seed', '{}'),
    ('1001', '2026-03-01', 'risk',      'dimension_score', 80.0, 80.0, 'pt', 'raw.risk.score',      'normalized_dimension_score', TRUE,  20.0, 'seed', '{}'),
    ('1001', '2026-03-02', 'product',   'dimension_score', 91.0, 91.0, 'pt', 'raw.product.score',   'normalized_dimension_score', FALSE, 0.0,  'seed', '{}'),
    ('1001', '2026-03-02', 'logistics', 'dimension_score', 87.0, 87.0, 'pt', 'raw.logistics.score', 'normalized_dimension_score', FALSE, 0.0,  'seed', '{}'),
    ('1001', '2026-03-02', 'service',   'dimension_score', 87.0, 87.0, 'pt', 'raw.service.score',   'normalized_dimension_score', FALSE, 0.0,  'seed', '{}'),
    ('1001', '2026-03-02', 'risk',      'dimension_score', 81.0, 81.0, 'pt', 'raw.risk.score',      'normalized_dimension_score', TRUE,  19.0, 'seed', '{}'),
    ('1001', '2026-03-03', 'product',   'dimension_score', 92.0, 92.0, 'pt', 'raw.product.score',   'normalized_dimension_score', FALSE, 0.0,  'seed', '{}'),
    ('1001', '2026-03-03', 'logistics', 'dimension_score', 89.0, 89.0, 'pt', 'raw.logistics.score', 'normalized_dimension_score', FALSE, 0.0,  'seed', '{}'),
    ('1001', '2026-03-03', 'service',   'dimension_score', 88.0, 88.0, 'pt', 'raw.service.score',   'normalized_dimension_score', FALSE, 0.0,  'seed', '{}'),
    ('1001', '2026-03-03', 'risk',      'dimension_score', 79.0, 79.0, 'pt', 'raw.risk.score',      'normalized_dimension_score', TRUE,  21.0, 'seed', '{}')
ON CONFLICT (shop_id, metric_date, dimension, metric_key)
DO UPDATE SET
    metric_score = EXCLUDED.metric_score,
    metric_value = EXCLUDED.metric_value,
    metric_unit = EXCLUDED.metric_unit,
    source_field = EXCLUDED.source_field,
    formula_expr = EXCLUDED.formula_expr,
    is_penalty = EXCLUDED.is_penalty,
    deduct_points = EXCLUDED.deduct_points,
    source = EXCLUDED.source,
    extra = EXCLUDED.extra;

-- product metric details
INSERT INTO experience_metric_daily (
    shop_id, metric_date, dimension, metric_key, metric_score, metric_value, metric_unit,
    source_field, formula_expr, is_penalty, deduct_points, source, extra
)
VALUES
    ('1001', '2026-03-03', 'product', 'product_quality_score',         93.0, 93.0, 'pt', 'raw.product.quality_score',          'weighted_quality_feedback', FALSE, 0.0, 'seed', '{}'),
    ('1001', '2026-03-03', 'product', 'product_return_rate',           89.0, 1.8,  '%',  'raw.product.return_rate',            'returns/orders*100',        FALSE, 0.0, 'seed', '{}'),
    ('1001', '2026-03-03', 'product', 'product_negative_review_rate',  87.0, 2.4,  '%',  'raw.product.negative_review_rate',   'negative_reviews/reviews*100', FALSE, 0.0, 'seed', '{}')
ON CONFLICT (shop_id, metric_date, dimension, metric_key)
DO UPDATE SET
    metric_score = EXCLUDED.metric_score,
    metric_value = EXCLUDED.metric_value,
    metric_unit = EXCLUDED.metric_unit,
    source_field = EXCLUDED.source_field,
    formula_expr = EXCLUDED.formula_expr,
    is_penalty = EXCLUDED.is_penalty,
    deduct_points = EXCLUDED.deduct_points,
    source = EXCLUDED.source,
    extra = EXCLUDED.extra;

-- logistics metric details
INSERT INTO experience_metric_daily (
    shop_id, metric_date, dimension, metric_key, metric_score, metric_value, metric_unit,
    source_field, formula_expr, is_penalty, deduct_points, source, extra
)
VALUES
    ('1001', '2026-03-03', 'logistics', 'pickup_sla',             90.0, 95.0, '%', 'raw.logistics.pickup_sla',       'pickup_in_24h_orders/fulfilled_orders*100', FALSE, 0.0, 'seed', '{}'),
    ('1001', '2026-03-03', 'logistics', 'delivery_sla',           88.0, 93.0, '%', 'raw.logistics.delivery_sla',     'delivery_in_72h_orders/fulfilled_orders*100', FALSE, 0.0, 'seed', '{}'),
    ('1001', '2026-03-03', 'logistics', 'logistics_return_rate',  87.0, 1.2,  '%', 'raw.logistics.damage_return_rate', 'damage_returns/delivered_orders*100', FALSE, 0.0, 'seed', '{}')
ON CONFLICT (shop_id, metric_date, dimension, metric_key)
DO UPDATE SET
    metric_score = EXCLUDED.metric_score,
    metric_value = EXCLUDED.metric_value,
    metric_unit = EXCLUDED.metric_unit,
    source_field = EXCLUDED.source_field,
    formula_expr = EXCLUDED.formula_expr,
    is_penalty = EXCLUDED.is_penalty,
    deduct_points = EXCLUDED.deduct_points,
    source = EXCLUDED.source,
    extra = EXCLUDED.extra;

-- service metric details
INSERT INTO experience_metric_daily (
    shop_id, metric_date, dimension, metric_key, metric_score, metric_value, metric_unit,
    source_field, formula_expr, is_penalty, deduct_points, source, extra
)
VALUES
    ('1001', '2026-03-03', 'service', 'response_latency',              86.0, 22.0, 's', 'raw.service.first_response_seconds',      'avg(first_response_seconds)', FALSE, 0.0, 'seed', '{}'),
    ('1001', '2026-03-03', 'service', 'after_sales_resolution_rate',   89.0, 92.0, '%', 'raw.service.after_sales_resolution_rate',  'resolved_after_sales/after_sales_total*100', FALSE, 0.0, 'seed', '{}'),
    ('1001', '2026-03-03', 'service', 'service_satisfaction',          90.0, 94.0, '%', 'raw.service.satisfaction_score',          'positive_service_reviews/service_reviews*100', FALSE, 0.0, 'seed', '{}')
ON CONFLICT (shop_id, metric_date, dimension, metric_key)
DO UPDATE SET
    metric_score = EXCLUDED.metric_score,
    metric_value = EXCLUDED.metric_value,
    metric_unit = EXCLUDED.metric_unit,
    source_field = EXCLUDED.source_field,
    formula_expr = EXCLUDED.formula_expr,
    is_penalty = EXCLUDED.is_penalty,
    deduct_points = EXCLUDED.deduct_points,
    source = EXCLUDED.source,
    extra = EXCLUDED.extra;

-- risk metric details
INSERT INTO experience_metric_daily (
    shop_id, metric_date, dimension, metric_key, metric_score, metric_value, metric_unit,
    source_field, formula_expr, is_penalty, deduct_points, source, extra
)
VALUES
    ('1001', '2026-03-03', 'risk', 'fake_transaction',             78.0, 22.0, 'pt', 'raw.risk.fake_transaction_cases',      'risk_penalty(fake_transaction_cases)', TRUE, 22.0, 'seed', '{"impact_score":14.3,"status":"processing","owner":"owner_7"}'),
    ('1001', '2026-03-03', 'risk', 'policy_violation',             84.0, 16.0, 'pt', 'raw.risk.policy_violation_cases',      'risk_penalty(policy_violation_cases)', TRUE, 16.0, 'seed', '{"impact_score":10.4,"status":"pending","owner":"owner_2"}'),
    ('1001', '2026-03-03', 'risk', 'customer_complaint_penalty',   88.0, 12.0, 'pt', 'raw.risk.customer_complaint_cases',    'risk_penalty(customer_complaint_cases)', TRUE, 12.0, 'seed', '{"impact_score":7.8,"status":"resolved","owner":"owner_3"}')
ON CONFLICT (shop_id, metric_date, dimension, metric_key)
DO UPDATE SET
    metric_score = EXCLUDED.metric_score,
    metric_value = EXCLUDED.metric_value,
    metric_unit = EXCLUDED.metric_unit,
    source_field = EXCLUDED.source_field,
    formula_expr = EXCLUDED.formula_expr,
    is_penalty = EXCLUDED.is_penalty,
    deduct_points = EXCLUDED.deduct_points,
    source = EXCLUDED.source,
    extra = EXCLUDED.extra;

-- issue rows
INSERT INTO experience_issue_daily (
    shop_id,
    metric_date,
    dimension,
    issue_key,
    issue_title,
    status,
    owner,
    impact_score,
    deduct_points,
    occurred_at,
    deadline_at,
    source,
    extra
)
VALUES
    ('1001', '2026-03-03', 'product', 'issue_1', 'product defect complaints', 'pending',  'owner_1', 18.5, 6.2, '2026-03-03T09:00:00+00:00', '2026-03-06T18:00:00+00:00', 'seed', '{}'),
    ('1001', '2026-03-02', 'risk',    'issue_2', 'policy violation warning',  'resolved', 'owner_2', 11.0, 3.0, '2026-03-02T08:00:00+00:00', NULL,                        'seed', '{}')
ON CONFLICT (shop_id, metric_date, issue_key)
DO UPDATE SET
    dimension = EXCLUDED.dimension,
    issue_title = EXCLUDED.issue_title,
    status = EXCLUDED.status,
    owner = EXCLUDED.owner,
    impact_score = EXCLUDED.impact_score,
    deduct_points = EXCLUDED.deduct_points,
    occurred_at = EXCLUDED.occurred_at,
    deadline_at = EXCLUDED.deadline_at,
    source = EXCLUDED.source,
    extra = EXCLUDED.extra;

COMMIT;
