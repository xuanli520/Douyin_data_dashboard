from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


ExperienceDimension = Literal["product", "logistics", "service", "risk"]
ExperienceDimensionWithAll = Literal["product", "logistics", "service", "risk", "all"]

SUPPORTED_EXPERIENCE_DIMENSIONS: tuple[ExperienceDimension, ...] = (
    "product",
    "logistics",
    "service",
    "risk",
)

DIMENSION_WEIGHTS: dict[ExperienceDimension, float] = {
    "product": 0.40,
    "logistics": 0.30,
    "service": 0.30,
    "risk": 0.00,
}


class MetricContract(BaseModel):
    metric_key: str
    title: str
    source_field: str
    formula: str
    unit: str
    weight: str
    deduct_points: bool


METRIC_CONTRACTS: dict[ExperienceDimension, list[MetricContract]] = {
    "product": [
        MetricContract(
            metric_key="product_quality_score",
            title="product_quality_score",
            source_field="raw.product.quality_score",
            formula="weighted_quality_feedback",
            unit="pt",
            weight="45%",
            deduct_points=False,
        ),
        MetricContract(
            metric_key="product_return_rate",
            title="product_return_rate",
            source_field="raw.product.return_rate",
            formula="returns/orders*100",
            unit="%",
            weight="30%",
            deduct_points=False,
        ),
        MetricContract(
            metric_key="product_negative_review_rate",
            title="product_negative_review_rate",
            source_field="raw.product.negative_review_rate",
            formula="negative_reviews/reviews*100",
            unit="%",
            weight="25%",
            deduct_points=False,
        ),
    ],
    "logistics": [
        MetricContract(
            metric_key="pickup_sla",
            title="pickup_sla",
            source_field="raw.logistics.pickup_sla",
            formula="pickup_in_24h_orders/fulfilled_orders*100",
            unit="%",
            weight="30%",
            deduct_points=False,
        ),
        MetricContract(
            metric_key="delivery_sla",
            title="delivery_sla",
            source_field="raw.logistics.delivery_sla",
            formula="delivery_in_72h_orders/fulfilled_orders*100",
            unit="%",
            weight="50%",
            deduct_points=False,
        ),
        MetricContract(
            metric_key="logistics_return_rate",
            title="logistics_return_rate",
            source_field="raw.logistics.damage_return_rate",
            formula="damage_returns/delivered_orders*100",
            unit="%",
            weight="20%",
            deduct_points=False,
        ),
    ],
    "service": [
        MetricContract(
            metric_key="response_latency",
            title="response_latency",
            source_field="raw.service.first_response_seconds",
            formula="avg(first_response_seconds)",
            unit="s",
            weight="40%",
            deduct_points=False,
        ),
        MetricContract(
            metric_key="after_sales_resolution_rate",
            title="after_sales_resolution_rate",
            source_field="raw.service.after_sales_resolution_rate",
            formula="resolved_after_sales/after_sales_total*100",
            unit="%",
            weight="35%",
            deduct_points=False,
        ),
        MetricContract(
            metric_key="service_satisfaction",
            title="service_satisfaction",
            source_field="raw.service.satisfaction_score",
            formula="positive_service_reviews/service_reviews*100",
            unit="%",
            weight="25%",
            deduct_points=False,
        ),
    ],
    "risk": [
        MetricContract(
            metric_key="fake_transaction",
            title="fake_transaction",
            source_field="raw.risk.fake_transaction_cases",
            formula="risk_penalty(fake_transaction_cases)",
            unit="pt",
            weight="40%",
            deduct_points=True,
        ),
        MetricContract(
            metric_key="policy_violation",
            title="policy_violation",
            source_field="raw.risk.policy_violation_cases",
            formula="risk_penalty(policy_violation_cases)",
            unit="pt",
            weight="35%",
            deduct_points=True,
        ),
        MetricContract(
            metric_key="customer_complaint_penalty",
            title="customer_complaint_penalty",
            source_field="raw.risk.customer_complaint_cases",
            formula="risk_penalty(customer_complaint_cases)",
            unit="pt",
            weight="25%",
            deduct_points=True,
        ),
    ],
}


def normalize_dimension(
    dimension: str | None,
    *,
    default: ExperienceDimension = "product",
) -> ExperienceDimension:
    if dimension in SUPPORTED_EXPERIENCE_DIMENSIONS:
        return dimension
    return default


def normalize_dimension_with_all(
    dimension: str | None,
) -> ExperienceDimensionWithAll:
    if dimension == "all":
        return "all"
    return normalize_dimension(dimension)


def metric_mapping_table_rows() -> list[dict[str, str | bool]]:
    rows: list[dict[str, str | bool]] = []
    for dimension in SUPPORTED_EXPERIENCE_DIMENSIONS:
        for item in METRIC_CONTRACTS[dimension]:
            rows.append(
                {
                    "dimension": dimension,
                    "metric_key": item.metric_key,
                    "source_field": item.source_field,
                    "formula": item.formula,
                    "unit": item.unit,
                    "deduct_points": item.deduct_points,
                }
            )
    return rows


class ExperienceDimensionScore(BaseModel):
    dimension: ExperienceDimension
    score: float
    weight: str
    rank: int


class ExperienceAlertSummary(BaseModel):
    critical: int
    warning: int
    info: int
    total: int
    unread: int


class ExperienceOverviewResponse(BaseModel):
    shop_id: int
    date_range: str
    overall_score: float
    dimensions: list[ExperienceDimensionScore]
    alerts: ExperienceAlertSummary


class ExperienceTrendPoint(BaseModel):
    date: str
    value: float


class ExperienceTrendResponse(BaseModel):
    shop_id: int
    dimension: ExperienceDimension
    date_range: str
    trend: list[ExperienceTrendPoint]


class ExperienceIssueItem(BaseModel):
    id: str
    shop_id: int
    dimension: ExperienceDimension
    title: str
    deduct_points: float
    impact_score: float
    status: str
    owner: str
    occurred_at: str
    deadline_at: str | None = None
    date_range: str


class ExperienceIssueListResponse(BaseModel):
    items: list[ExperienceIssueItem]
    meta: dict[str, int | bool]


class MetricSubMetric(BaseModel):
    id: str
    title: str
    score: float
    weight: str
    value: str
    desc: str
    deduct_points: float | None = None
    impact_score: float | None = None
    status: str | None = None
    owner: str | None = None
    deadline_at: str | None = None


class MetricDetailResponse(BaseModel):
    shop_id: int
    metric_type: ExperienceDimension
    period: str
    date_range: str
    category_score: float
    sub_metrics: list[MetricSubMetric]
    score_ranges: list[dict[str, str | int]]
    formula: str
    trend: list[ExperienceTrendPoint]


class ExperienceDrilldownResponse(BaseModel):
    shop_id: int
    dimension: ExperienceDimension
    date_range: str
    category_score: float
    sub_metrics: list[MetricSubMetric]
    score_ranges: list[dict[str, str | int]]
    formula: str
    trend: list[ExperienceTrendPoint]
    issues: ExperienceIssueListResponse


class DashboardOverviewResponse(BaseModel):
    shop_id: int
    date_range: str
    cards: dict[str, int | float | str]


class DashboardKpiItem(BaseModel):
    id: str
    value: int | float | str
    change: str


class DashboardKpisTrendPoint(BaseModel):
    date: str
    orders: int
    gmv: float


class DashboardKpisResponse(BaseModel):
    shop_id: int
    date_range: str
    kpis: list[DashboardKpiItem]
    trend: list[DashboardKpisTrendPoint]
