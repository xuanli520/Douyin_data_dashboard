from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import date, datetime, timedelta

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.cache import CacheProtocol, get_cache
from src.config import get_settings
from src.domains.experience.presentation_mapper import (
    build_dashboard_kpis,
    build_dashboard_overview,
    build_issues,
    build_metric_detail,
    build_overview,
    build_trend,
)
from src.domains.experience.schemas import (
    DIMENSION_WEIGHTS,
    DashboardKpisResponse,
    DashboardOverviewResponse,
    ExperienceDrilldownResponse,
    ExperienceIssueListResponse,
    ExperienceOverviewResponse,
    ExperienceTrendResponse,
    MetricDetailResponse,
    normalize_dimension,
    normalize_dimension_with_all,
)
from src.domains.shop_dashboard.repository import ShopDashboardRepository
from src.exceptions import BusinessException
from src.session import get_session
from src.shared.errors import ErrorCode
from src.shared.redis_keys import redis_keys

MAX_DATE_RANGE_DAYS = 365


class ExperienceQueryService:
    def __init__(
        self,
        repo: ShopDashboardRepository,
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
        materials = await self.repo.list_display_materials(
            shop_id=str(shop_id),
            start_date=start_date,
            end_date=end_date,
        )
        payload = build_overview(
            shop_id=shop_id,
            date_range=normalized_range,
            materials=materials,
            dimension_weights=DIMENSION_WEIGHTS,
        )
        return ExperienceOverviewResponse.model_validate(payload)

    async def get_trend(
        self,
        *,
        shop_id: int,
        dimension: str | None,
        date_range: str | None,
    ) -> ExperienceTrendResponse:
        start_date, end_date, normalized_range = self._parse_date_range(date_range)
        normalized_dimension = normalize_dimension(dimension)
        materials = await self.repo.list_display_materials(
            shop_id=str(shop_id),
            start_date=start_date,
            end_date=end_date,
        )
        payload = build_trend(
            shop_id=shop_id,
            dimension=normalized_dimension,
            date_range=normalized_range,
            materials=materials,
        )
        return ExperienceTrendResponse.model_validate(payload)

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

        materials = await self.repo.list_display_materials(
            shop_id=str(shop_id),
            start_date=start_date,
            end_date=end_date,
        )
        payload = build_issues(
            shop_id=shop_id,
            date_range=normalized_range,
            materials=materials,
            dimension=normalized_dimension,
            status=normalized_status,
            page=page,
            size=size,
        )
        response = ExperienceIssueListResponse.model_validate(payload)
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

        materials = await self.repo.list_display_materials(
            shop_id=str(shop_id),
            start_date=start_date,
            end_date=end_date,
        )
        payload = build_metric_detail(
            shop_id=shop_id,
            metric_type=normalized_dimension,
            period=period,
            date_range=normalized_range,
            materials=materials,
        )
        response = MetricDetailResponse.model_validate(payload)
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

        materials = await self.repo.list_display_materials(
            shop_id=str(shop_id),
            start_date=start_date,
            end_date=end_date,
        )
        overview_payload = build_overview(
            shop_id=shop_id,
            date_range=normalized_range,
            materials=materials,
            dimension_weights=DIMENSION_WEIGHTS,
        )
        payload = build_dashboard_overview(
            shop_id=shop_id,
            date_range=normalized_range,
            materials=materials,
            overview_payload=overview_payload,
        )
        response = DashboardOverviewResponse.model_validate(payload)
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

        materials = await self.repo.list_display_materials(
            shop_id=str(shop_id),
            start_date=start_date,
            end_date=end_date,
        )
        dashboard_overview = await self.get_dashboard_overview(
            shop_id=shop_id,
            date_range=normalized_range,
        )
        payload = build_dashboard_kpis(
            shop_id=shop_id,
            date_range=normalized_range,
            materials=materials,
            overview_payload=dashboard_overview.model_dump(),
        )
        response = DashboardKpisResponse.model_validate(payload)
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
                raise BusinessException(
                    ErrorCode.EXPERIENCE_DATE_RANGE_TOO_LARGE,
                    (
                        "date_range is too large: "
                        f"maximum supported window is {MAX_DATE_RANGE_DAYS} days"
                    ),
                    data={"max_days": MAX_DATE_RANGE_DAYS, "days": days},
                )
            return today - timedelta(days=days - 1), today, f"{days}d"

        return today - timedelta(days=29), today, "30d"

    @staticmethod
    def _ensure_date_range_limit(start: date, end: date) -> None:
        days = (end - start).days + 1
        if days > MAX_DATE_RANGE_DAYS:
            raise BusinessException(
                ErrorCode.EXPERIENCE_DATE_RANGE_TOO_LARGE,
                (
                    "date_range is too large: "
                    f"maximum supported window is {MAX_DATE_RANGE_DAYS} days"
                ),
                data={
                    "max_days": MAX_DATE_RANGE_DAYS,
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "days": days,
                },
            )


async def get_experience_service(
    session: AsyncSession = Depends(get_session),
    cache: CacheProtocol = Depends(get_cache),
) -> AsyncGenerator[ExperienceQueryService, None]:
    yield ExperienceQueryService(
        repo=ShopDashboardRepository(session=session),
        cache=cache,
    )
