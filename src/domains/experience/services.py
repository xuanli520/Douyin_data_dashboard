from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import AsyncGenerator
from datetime import date, datetime, timedelta
from math import ceil

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.cache import CacheProtocol, get_cache
from src.config import get_settings
from src.domains.experience.models import ExperienceIssueDaily, ExperienceMetricDaily
from src.domains.experience.repository import ExperienceRepository
from src.domains.experience.schemas import (
    DIMENSION_WEIGHTS,
    METRIC_CONTRACTS,
    SUPPORTED_EXPERIENCE_DIMENSIONS,
    DashboardKpiItem,
    DashboardKpisResponse,
    DashboardKpisTrendPoint,
    DashboardOverviewResponse,
    ExperienceAlertSummary,
    ExperienceDimension,
    ExperienceDimensionScore,
    ExperienceDrilldownResponse,
    ExperienceIssueItem,
    ExperienceIssueListResponse,
    ExperienceOverviewResponse,
    ExperienceTrendPoint,
    ExperienceTrendResponse,
    MetricDetailResponse,
    MetricSubMetric,
    normalize_dimension,
    normalize_dimension_with_all,
)
from src.session import get_session
from src.shared.redis_keys import redis_keys


DIMENSION_SCORE_KEY = "dimension_score"
MAX_DATE_RANGE_DAYS = 365


def _build_pagination_meta(page: int, size: int, total: int) -> dict[str, int | bool]:
    size = max(size, 1)
    page = max(page, 1)
    pages = max(ceil(total / size), 1) if total else 0
    return {
        "page": page,
        "size": size,
        "total": total,
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1 and pages > 0,
    }


class ExperienceQueryService:
    def __init__(
        self,
        repo: ExperienceRepository,
        cache: CacheProtocol | None = None,
    ):
        self.repo = repo
        self.cache = cache
        cache_settings = get_settings().cache
        self.metrics_ttl_seconds = cache_settings.experience_metrics_ttl_seconds
        self.dashboard_ttl_seconds = cache_settings.experience_dashboard_ttl_seconds
        self.issues_ttl_seconds = cache_settings.experience_issues_ttl_seconds
        self.cache_index_ttl_seconds = cache_settings.experience_cache_index_ttl_seconds

    async def get_overview(
        self,
        *,
        shop_id: int,
        date_range: str | None,
    ) -> ExperienceOverviewResponse:
        start_date, end_date, normalized_range = self._parse_date_range(date_range)
        shop_key = str(shop_id)

        metric_rows = await self.repo.list_metric_rows(
            shop_id=shop_key,
            start_date=start_date,
            end_date=end_date,
            metric_key=DIMENSION_SCORE_KEY,
        )
        latest_scores = self._latest_scores_by_dimension(metric_rows)
        risk_deduct_points = self._latest_risk_deduct_points(metric_rows)

        ranked_dimensions = sorted(
            (
                (dimension, latest_scores.get(dimension, 0.0))
                for dimension in SUPPORTED_EXPERIENCE_DIMENSIONS
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        rank_map = {
            dimension: index + 1
            for index, (dimension, _) in enumerate(ranked_dimensions)
        }

        dimensions: list[ExperienceDimensionScore] = []
        for dimension in SUPPORTED_EXPERIENCE_DIMENSIONS:
            score = round(latest_scores.get(dimension, 0.0), 2)
            dimensions.append(
                ExperienceDimensionScore(
                    dimension=dimension,
                    score=score,
                    weight=f"{int(DIMENSION_WEIGHTS[dimension] * 100)}%",
                    rank=rank_map[dimension],
                )
            )

        overall_score = round(
            sum(
                latest_scores.get(dimension, 0.0) * DIMENSION_WEIGHTS[dimension]
                for dimension in SUPPORTED_EXPERIENCE_DIMENSIONS
            )
            - risk_deduct_points,
            2,
        )

        issue_rows = await self.repo.list_issue_rows(
            shop_id=shop_key,
            start_date=start_date,
            end_date=end_date,
        )
        alerts = self._build_alert_summary(issue_rows)

        return ExperienceOverviewResponse(
            shop_id=shop_id,
            date_range=normalized_range,
            overall_score=overall_score,
            dimensions=dimensions,
            alerts=alerts,
        )

    async def get_trend(
        self,
        *,
        shop_id: int,
        dimension: str | None,
        date_range: str | None,
    ) -> ExperienceTrendResponse:
        start_date, end_date, normalized_range = self._parse_date_range(date_range)
        normalized_dimension = normalize_dimension(dimension)
        shop_key = str(shop_id)
        rows = await self.repo.list_metric_rows(
            shop_id=shop_key,
            start_date=start_date,
            end_date=end_date,
            dimension=normalized_dimension,
            metric_key=DIMENSION_SCORE_KEY,
        )
        points = [
            ExperienceTrendPoint(
                date=row.metric_date.isoformat(), value=round(row.metric_score, 2)
            )
            for row in rows
        ]
        return ExperienceTrendResponse(
            shop_id=shop_id,
            dimension=normalized_dimension,
            date_range=normalized_range,
            trend=points,
        )

    async def get_issues(
        self,
        *,
        shop_id: int,
        dimension: str | None,
        status: str | None,
        date_range: str | None,
        page: int,
        size: int,
    ) -> ExperienceIssueListResponse:
        start_date, end_date, normalized_range = self._parse_date_range(date_range)
        normalized_dimension = normalize_dimension_with_all(dimension)
        normalized_status = (
            "all" if status in {None, "", "all"} else str(status).strip() or "all"
        )
        cache_key = redis_keys.experience_issues(
            shop_id=shop_id,
            dimension=normalized_dimension,
            status=normalized_status,
            date_range=normalized_range,
            page=page,
            size=size,
        )
        cached = await self._cache_get_model(cache_key, ExperienceIssueListResponse)
        if cached is not None:
            return cached

        filtered_dimension = (
            None if normalized_dimension == "all" else normalized_dimension
        )
        filtered_status = None if normalized_status == "all" else normalized_status

        rows, total = await self.repo.list_issues(
            shop_id=str(shop_id),
            start_date=start_date,
            end_date=end_date,
            dimension=filtered_dimension,
            status=filtered_status,
            page=page,
            size=size,
        )
        items = [
            self._to_issue_item(shop_id=shop_id, row=row, date_range=normalized_range)
            for row in rows
        ]
        response = ExperienceIssueListResponse(
            items=items,
            meta=_build_pagination_meta(page=page, size=size, total=total),
        )
        await self._cache_set_model(
            cache_key,
            response,
            ttl_seconds=self.issues_ttl_seconds,
            shop_id=shop_id,
            start_date=start_date,
            end_date=end_date,
        )
        return response

    async def get_metric_detail(
        self,
        *,
        shop_id: int,
        metric_type: str,
        period: str,
        date_range: str | None,
    ) -> MetricDetailResponse:
        start_date, end_date, normalized_range = self._parse_date_range(date_range)
        normalized_dimension = normalize_dimension(metric_type)
        shop_key = str(shop_id)
        cache_key = redis_keys.experience_metrics(
            shop_id=shop_id,
            dimension=normalized_dimension,
            date_range=normalized_range,
        )
        cached = await self._cache_get_model(cache_key, MetricDetailResponse)
        if cached is not None:
            if cached.period != period:
                return cached.model_copy(update={"period": period})
            return cached

        trend_response = await self.get_trend(
            shop_id=shop_id,
            dimension=normalized_dimension,
            date_range=normalized_range,
        )
        latest_date = await self.repo.get_latest_metric_date(
            shop_id=shop_key,
            start_date=start_date,
            end_date=end_date,
            dimension=normalized_dimension,
        )
        latest_rows = []
        if latest_date is not None:
            latest_rows = await self.repo.list_rows_for_metric_date(
                shop_id=shop_key,
                metric_date=latest_date,
                dimension=normalized_dimension,
            )
        row_by_metric = {row.metric_key: row for row in latest_rows}

        contracts = METRIC_CONTRACTS[normalized_dimension]
        sub_metrics: list[MetricSubMetric] = []
        for contract in contracts:
            row = row_by_metric.get(contract.metric_key)
            score = round(row.metric_score if row else 0.0, 2)
            raw_value = row.metric_value if row else 0.0
            value = self._format_metric_value(raw_value, contract.unit)

            payload = {
                "id": contract.metric_key,
                "title": contract.title,
                "score": score,
                "weight": contract.weight,
                "value": value,
                "desc": contract.formula,
            }
            if contract.deduct_points:
                deduct = round(row.deduct_points if row else 0.0, 2)
                payload.update(
                    {
                        "deduct_points": deduct,
                        "impact_score": round(
                            float((row.extra or {}).get("impact_score", deduct * 0.65))
                            if row
                            else 0.0,
                            2,
                        ),
                        "status": str((row.extra or {}).get("status", "pending"))
                        if row
                        else "pending",
                        "owner": str((row.extra or {}).get("owner", "")) if row else "",
                        "deadline_at": str((row.extra or {}).get("deadline_at", ""))
                        if row
                        else "",
                    }
                )
            sub_metrics.append(MetricSubMetric(**payload))

        dimension_score_row = row_by_metric.get(DIMENSION_SCORE_KEY)
        category_score = (
            round(dimension_score_row.metric_score, 2)
            if dimension_score_row
            else round(
                sum(metric.score for metric in sub_metrics) / max(len(sub_metrics), 1),
                2,
            )
        )
        score_ranges = self._build_score_ranges(sub_metrics)
        formula = " + ".join(
            f"{contract.metric_key}*{contract.weight}" for contract in contracts
        )

        response = MetricDetailResponse(
            shop_id=shop_id,
            metric_type=normalized_dimension,
            period=period,
            date_range=normalized_range,
            category_score=category_score,
            sub_metrics=sub_metrics,
            score_ranges=score_ranges,
            formula=formula,
            trend=trend_response.trend,
        )
        await self._cache_set_model(
            cache_key,
            response,
            ttl_seconds=self.metrics_ttl_seconds,
            shop_id=shop_id,
            start_date=start_date,
            end_date=end_date,
        )
        return response

    async def get_drilldown(
        self,
        *,
        shop_id: int,
        dimension: str,
        date_range: str | None,
        page: int,
        size: int,
    ) -> ExperienceDrilldownResponse:
        normalized_dimension = normalize_dimension(dimension)
        metric_detail = await self.get_metric_detail(
            shop_id=shop_id,
            metric_type=normalized_dimension,
            period="30d",
            date_range=date_range,
        )
        issues = await self.get_issues(
            shop_id=shop_id,
            dimension=normalized_dimension,
            status="all",
            date_range=date_range,
            page=page,
            size=size,
        )
        return ExperienceDrilldownResponse(
            shop_id=metric_detail.shop_id,
            dimension=metric_detail.metric_type,
            date_range=metric_detail.date_range,
            category_score=metric_detail.category_score,
            sub_metrics=metric_detail.sub_metrics,
            score_ranges=metric_detail.score_ranges,
            formula=metric_detail.formula,
            trend=metric_detail.trend,
            issues=issues,
        )

    async def get_dashboard_overview(
        self,
        *,
        shop_id: int,
        date_range: str | None,
    ) -> DashboardOverviewResponse:
        start_date, end_date, normalized_range = self._parse_date_range(date_range)
        cache_key = redis_keys.experience_dashboard(
            shop_id=shop_id,
            date_range=normalized_range,
            section="overview",
        )
        cached = await self._cache_get_model(cache_key, DashboardOverviewResponse)
        if cached is not None:
            return cached

        overview = await self.get_overview(shop_id=shop_id, date_range=normalized_range)
        metrics = await self.repo.list_metric_rows(
            shop_id=str(shop_id),
            start_date=start_date,
            end_date=end_date,
            metric_key=DIMENSION_SCORE_KEY,
        )

        orders = len(metrics) * 10
        gmv = round(overview.overall_score * max(orders, 1) * 1.2, 2) if orders else 0.0
        average_order_value = round(gmv / orders, 2) if orders else 0.0

        refund_row = await self.repo.get_latest_metric_row(
            shop_id=str(shop_id),
            start_date=start_date,
            end_date=end_date,
            metric_key="product_return_rate",
        )
        refund_rate_value = refund_row.metric_value if refund_row else 0.0
        conversion_rate_value = round(min(99.0, overview.overall_score / 1.2), 2)

        response = DashboardOverviewResponse(
            shop_id=shop_id,
            date_range=normalized_range,
            cards={
                "orders": orders,
                "gmv": gmv,
                "average_order_value": average_order_value,
                "refund_rate": f"{round(refund_rate_value, 2)}%",
                "conversion_rate": f"{conversion_rate_value}%",
            },
        )
        await self._cache_set_model(
            cache_key,
            response,
            ttl_seconds=self.dashboard_ttl_seconds,
            shop_id=shop_id,
            start_date=start_date,
            end_date=end_date,
        )
        return response

    async def get_dashboard_kpis(
        self,
        *,
        shop_id: int,
        date_range: str | None,
    ) -> DashboardKpisResponse:
        start_date, end_date, normalized_range = self._parse_date_range(date_range)
        cache_key = redis_keys.experience_dashboard(
            shop_id=shop_id,
            date_range=normalized_range,
            section="kpis",
        )
        cached = await self._cache_get_model(cache_key, DashboardKpisResponse)
        if cached is not None:
            return cached

        overview = await self.get_dashboard_overview(
            shop_id=shop_id, date_range=normalized_range
        )
        metric_rows = await self.repo.list_metric_rows(
            shop_id=str(shop_id),
            start_date=start_date,
            end_date=end_date,
            metric_key=DIMENSION_SCORE_KEY,
        )

        scores_by_day: dict[date, list[float]] = defaultdict(list)
        for row in metric_rows:
            scores_by_day[row.metric_date].append(row.metric_score)

        trend_points: list[DashboardKpisTrendPoint] = []
        for metric_date in sorted(scores_by_day):
            daily_scores = scores_by_day[metric_date]
            avg_score = sum(daily_scores) / max(len(daily_scores), 1)
            orders = int(round(avg_score * 10))
            gmv = round(orders * avg_score, 2)
            trend_points.append(
                DashboardKpisTrendPoint(
                    date=metric_date.isoformat(),
                    orders=orders,
                    gmv=gmv,
                )
            )

        first_orders = trend_points[0].orders if trend_points else 0
        last_orders = trend_points[-1].orders if trend_points else 0
        first_gmv = trend_points[0].gmv if trend_points else 0.0
        last_gmv = trend_points[-1].gmv if trend_points else 0.0

        refund_rows = await self.repo.list_metric_rows(
            shop_id=str(shop_id),
            start_date=start_date,
            end_date=end_date,
            metric_key="product_return_rate",
        )
        refund_first = refund_rows[0].metric_value if refund_rows else 0.0
        refund_last = refund_rows[-1].metric_value if refund_rows else 0.0

        response = DashboardKpisResponse(
            shop_id=shop_id,
            date_range=normalized_range,
            kpis=[
                DashboardKpiItem(
                    id="orders",
                    value=trend_points[-1].orders if trend_points else 0,
                    change=self._format_change(first_orders, last_orders),
                ),
                DashboardKpiItem(
                    id="gmv",
                    value=trend_points[-1].gmv if trend_points else 0.0,
                    change=self._format_change(first_gmv, last_gmv),
                ),
                DashboardKpiItem(
                    id="refund_rate",
                    value=overview.cards["refund_rate"],
                    change=self._format_change(refund_first, refund_last),
                ),
            ],
            trend=trend_points,
        )
        await self._cache_set_model(
            cache_key,
            response,
            ttl_seconds=self.dashboard_ttl_seconds,
            shop_id=shop_id,
            start_date=start_date,
            end_date=end_date,
        )
        return response

    async def invalidate_shop_date(
        self,
        *,
        shop_id: int | str,
        metric_date: date,
    ) -> int:
        if self.cache is None:
            return 0

        date_text = metric_date.isoformat()
        index_key = redis_keys.experience_cache_date_index(
            shop_id=shop_id,
            metric_date=date_text,
        )
        cache_keys = await self._load_cache_index_keys(index_key)
        if not cache_keys:
            return 0

        deleted = 0
        for cache_key in cache_keys:
            if await self.cache.delete(cache_key):
                deleted += 1
        await self.cache.delete(index_key)
        return deleted

    async def _cache_get_model(self, key: str, model_type):
        if self.cache is None:
            return None
        payload = await self.cache.get(key)
        if payload is None:
            return None
        try:
            return model_type.model_validate_json(payload)
        except ValueError:
            await self.cache.delete(key)
            return None

    async def _cache_set_model(
        self,
        key: str,
        value,
        *,
        ttl_seconds: int,
        shop_id: int,
        start_date: date,
        end_date: date,
    ) -> None:
        if self.cache is None:
            return
        await self.cache.set(key, value.model_dump_json(), ttl=max(ttl_seconds, 1))
        await self._append_cache_index_keys(
            key=key,
            shop_id=shop_id,
            start_date=start_date,
            end_date=end_date,
        )

    async def _append_cache_index_keys(
        self,
        *,
        key: str,
        shop_id: int,
        start_date: date,
        end_date: date,
    ) -> None:
        if self.cache is None:
            return
        index_ttl = max(self.cache_index_ttl_seconds, 1)
        for metric_date in self._iterate_metric_dates(start_date, end_date):
            index_key = redis_keys.experience_cache_date_index(
                shop_id=shop_id,
                metric_date=metric_date.isoformat(),
            )
            if await self._append_cache_index_key_atomic(
                index_key=index_key,
                cache_key=key,
                ttl_seconds=index_ttl,
            ):
                continue
            try:
                current_raw = await self.cache.get(index_key)
            except Exception:
                current_raw = None
            keys = self._decode_cache_key_list(current_raw)
            if key not in keys:
                keys.append(key)
            await self.cache.set(
                index_key,
                json.dumps(keys, separators=(",", ":")),
                ttl=index_ttl,
            )

    async def _append_cache_index_key_atomic(
        self,
        *,
        index_key: str,
        cache_key: str,
        ttl_seconds: int,
    ) -> bool:
        redis_client = self._get_redis_client()
        if redis_client is None:
            return False
        try:
            await redis_client.eval(
                (
                    "redis.call('SADD', KEYS[1], ARGV[1]);"
                    "local ttl=tonumber(ARGV[2]);"
                    "if ttl and ttl>0 then redis.call('EXPIRE', KEYS[1], ttl); end;"
                    "return 1;"
                ),
                1,
                index_key,
                cache_key,
                str(ttl_seconds),
            )
            return True
        except Exception:
            return False

    async def _load_cache_index_keys(self, index_key: str) -> list[str]:
        if self.cache is None:
            return []
        redis_client = self._get_redis_client()
        if redis_client is not None:
            try:
                key_type = await redis_client.type(index_key)
                key_type_text = (
                    key_type.decode("utf-8", errors="ignore")
                    if isinstance(key_type, bytes)
                    else str(key_type)
                )
                if key_type_text == "set":
                    members = await redis_client.smembers(index_key)
                    return self._normalize_cache_key_items(list(members))
            except Exception:
                return []

        try:
            cached_raw = await self.cache.get(index_key)
        except Exception:
            return []
        return self._decode_cache_key_list(cached_raw)

    def _get_redis_client(self):
        if self.cache is None:
            return None
        return getattr(self.cache, "client", None)

    @staticmethod
    def _iterate_metric_dates(start_date: date, end_date: date) -> list[date]:
        if end_date < start_date:
            return [start_date]
        days = (end_date - start_date).days
        return [start_date + timedelta(days=offset) for offset in range(days + 1)]

    @staticmethod
    def _decode_cache_key_list(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except ValueError:
            return []
        if not isinstance(parsed, list):
            return []
        return ExperienceQueryService._normalize_cache_key_items(parsed)

    @staticmethod
    def _normalize_cache_key_items(items: list[object]) -> list[str]:
        keys: list[str] = []
        for item in items:
            if isinstance(item, bytes):
                text = item.decode("utf-8", errors="ignore").strip()
            else:
                text = str(item or "").strip()
            if text and text not in keys:
                keys.append(text)
        return keys

    @staticmethod
    def _parse_date_range(date_range: str | None) -> tuple[date, date, str]:
        today = date.today()
        if not date_range:
            return today - timedelta(days=29), today, "30d"

        clean = date_range.strip()
        if "," in clean:
            start_raw, end_raw = [part.strip() for part in clean.split(",", 1)]
            try:
                start = datetime.strptime(start_raw, "%Y-%m-%d").date()
                end = datetime.strptime(end_raw, "%Y-%m-%d").date()
                if start <= end:
                    ExperienceQueryService._ensure_date_range_limit(start, end)
                    return start, end, f"{start.isoformat()},{end.isoformat()}"
            except ValueError:
                pass

        if clean.endswith("d") and clean[:-1].isdigit():
            days = max(int(clean[:-1]), 1)
            if days > MAX_DATE_RANGE_DAYS:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "date_range is too large: "
                        f"maximum supported window is {MAX_DATE_RANGE_DAYS} days"
                    ),
                )
            return today - timedelta(days=days - 1), today, f"{days}d"

        return today - timedelta(days=29), today, "30d"

    @staticmethod
    def _ensure_date_range_limit(start: date, end: date) -> None:
        days = (end - start).days + 1
        if days > MAX_DATE_RANGE_DAYS:
            raise HTTPException(
                status_code=422,
                detail=(
                    "date_range is too large: "
                    f"maximum supported window is {MAX_DATE_RANGE_DAYS} days"
                ),
            )

    @staticmethod
    def _latest_scores_by_dimension(
        rows: list[ExperienceMetricDaily],
    ) -> dict[ExperienceDimension, float]:
        latest: dict[ExperienceDimension, tuple[date, float]] = {}
        for row in rows:
            if row.dimension not in SUPPORTED_EXPERIENCE_DIMENSIONS:
                continue
            metric_date = row.metric_date
            previous = latest.get(row.dimension)
            if previous is None or metric_date >= previous[0]:
                latest[row.dimension] = (metric_date, float(row.metric_score))
        return {dimension: score for dimension, (_, score) in latest.items()}

    @staticmethod
    def _latest_risk_deduct_points(rows: list[ExperienceMetricDaily]) -> float:
        latest_risk: tuple[date, float, float] | None = None
        for row in rows:
            if row.dimension != "risk":
                continue
            metric_date = row.metric_date
            current = (metric_date, float(row.metric_score), float(row.deduct_points))
            if latest_risk is None or metric_date >= latest_risk[0]:
                latest_risk = current

        if latest_risk is None:
            return 0.0

        _, risk_score, deduct_points = latest_risk
        if deduct_points > 0:
            return round(deduct_points, 2)
        return round(max(0.0, 100.0 - risk_score), 2)

    @staticmethod
    def _build_alert_summary(
        rows: list[ExperienceIssueDaily],
    ) -> ExperienceAlertSummary:
        critical = 0
        warning = 0
        info = 0
        unread = 0
        for row in rows:
            if row.impact_score >= 15:
                critical += 1
            elif row.impact_score >= 8:
                warning += 1
            else:
                info += 1
            if row.status in {"pending", "processing"}:
                unread += 1
        return ExperienceAlertSummary(
            critical=critical,
            warning=warning,
            info=info,
            total=len(rows),
            unread=unread,
        )

    @staticmethod
    def _to_issue_item(
        *,
        shop_id: int,
        row: ExperienceIssueDaily,
        date_range: str,
    ) -> ExperienceIssueItem:
        return ExperienceIssueItem(
            id=row.issue_key,
            shop_id=shop_id,
            dimension=normalize_dimension(row.dimension),
            title=row.issue_title,
            deduct_points=round(row.deduct_points, 2),
            impact_score=round(row.impact_score, 2),
            status=row.status,
            owner=row.owner,
            occurred_at=row.occurred_at.isoformat(),
            deadline_at=row.deadline_at.isoformat() if row.deadline_at else None,
            date_range=date_range,
        )

    @staticmethod
    def _build_score_ranges(
        sub_metrics: list[MetricSubMetric],
    ) -> list[dict[str, str | int]]:
        excellent = len([metric for metric in sub_metrics if metric.score >= 90])
        good = len([metric for metric in sub_metrics if 80 <= metric.score < 90])
        attention = len([metric for metric in sub_metrics if metric.score < 80])
        return [
            {"label": "excellent", "range": "90-100", "count": excellent},
            {"label": "good", "range": "80-89", "count": good},
            {"label": "attention", "range": "0-79", "count": attention},
        ]

    @staticmethod
    def _format_metric_value(value: float, unit: str) -> str:
        rounded = round(float(value), 2)
        if unit == "%":
            return f"{rounded}%"
        if unit == "s":
            return f"{rounded}s"
        return f"{rounded}{unit}"

    @staticmethod
    def _format_change(first: float | int, last: float | int) -> str:
        first_value = float(first)
        last_value = float(last)
        if first_value == 0:
            delta = 0.0 if last_value == 0 else 100.0
        else:
            delta = ((last_value - first_value) / abs(first_value)) * 100
        sign = "+" if delta >= 0 else ""
        return f"{sign}{round(delta, 2)}%"


async def get_experience_service(
    session: AsyncSession = Depends(get_session),
    cache: CacheProtocol = Depends(get_cache),
) -> AsyncGenerator[ExperienceQueryService, None]:
    yield ExperienceQueryService(
        repo=ExperienceRepository(session=session),
        cache=cache,
    )
