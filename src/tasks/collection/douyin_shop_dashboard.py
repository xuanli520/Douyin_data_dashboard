from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.domains.data_source.enums import DataSourceStatus, ScrapingRuleStatus
from src.domains.data_source.repository import (
    DataSourceRepository,
    ScrapingRuleRepository,
)
from src.domains.shop_dashboard.repository import ShopDashboardRepository
from src.scrapers.shop_dashboard.browser_scraper import BrowserScraper
from src.scrapers.shop_dashboard.http_scraper import HttpScraper
from src.scrapers.shop_dashboard.lock_manager import LockManager
from src.scrapers.shop_dashboard.login_state_manager import LoginStateManager
from src.scrapers.shop_dashboard.runtime import (
    ShopDashboardRuntimeConfig,
    build_runtime_config,
)
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore
from src.session import async_session_factory
from src.tasks.base import TaskStatusMixin
from src.tasks.exceptions import ScrapingFailedException
from src.tasks.funboost_compat import boost, fct
from src.tasks.idempotency import FunboostIdempotencyHelper
from src.tasks.params import CollectionTaskParams

logger = logging.getLogger(__name__)


def _write_started_status(task_func, task_name: str, triggered_by: int | None) -> None:
    try:
        redis_client = task_func.publisher.redis_db_frame
        task_id = str(getattr(fct, "task_id", "unknown"))
        key = f"douyin:task:status:{task_id}"
        redis_client.hset(
            key,
            mapping={
                "status": "STARTED",
                "started_at": time.time(),
                "task_name": task_name,
                "triggered_by": triggered_by if triggered_by is not None else "",
            },
        )
        redis_client.expire(key, get_settings().funboost.status_ttl_seconds)
    except Exception:
        logger.exception("failed to write started task status: %s", task_name)


@boost(
    CollectionTaskParams(
        queue_name="collection_shop_dashboard",
        consumer_override_cls=TaskStatusMixin,
        is_push_to_dlx_queue_when_retry_max_times=True,
    )
)
def sync_shop_dashboard(
    data_source_id: int,
    rule_id: int,
    execution_id: str,
    triggered_by: int | None = None,
) -> dict[str, Any]:
    _write_started_status(sync_shop_dashboard, "sync_shop_dashboard", triggered_by)
    redis_client = sync_shop_dashboard.publisher.redis_db_frame
    helper = FunboostIdempotencyHelper(
        redis_client=redis_client, task_name="sync_shop_dashboard"
    )
    runtime = _run_async(
        _load_runtime_config(
            data_source_id=data_source_id,
            rule_id=rule_id,
            execution_id=execution_id,
        )
    )
    if runtime.granularity != "DAY":
        raise ScrapingFailedException(
            "Unsupported granularity",
            error_data={"granularity": runtime.granularity},
        )

    metric_dates = _resolve_metric_dates(runtime)
    browser = BrowserScraper()
    items: list[dict[str, Any]] = []
    for metric_date in metric_dates:
        business_key = _build_business_key(runtime, metric_date)
        cached = helper.get_cached_result(business_key)
        if cached:
            items.append(cached)
            continue

        token = helper.acquire_lock(
            business_key, ttl=get_settings().shop_dashboard.lock_ttl_seconds
        )
        if not token:
            items.append(
                {
                    "status": "skipped",
                    "reason": "running",
                    "metric_date": metric_date,
                    "shop_id": runtime.shop_id,
                    "rule_id": runtime.rule_id,
                    "execution_id": runtime.execution_id,
                }
            )
            continue

        try:
            collected = _collect_one_day(runtime, metric_date, browser)
            _run_async(_persist_result(runtime, metric_date, collected))
            helper.cache_result(business_key, collected)
            items.append(collected)
        finally:
            helper.release_lock(business_key, token)

    return {
        "status": "success",
        "data_source_id": data_source_id,
        "rule_id": rule_id,
        "execution_id": execution_id,
        "items": items,
    }


@boost(
    CollectionTaskParams(
        queue_name="collection_shop_dashboard_dlx",
        consumer_override_cls=TaskStatusMixin,
    )
)
def handle_collection_shop_dashboard_dead_letter(**payload) -> dict[str, Any]:
    return {
        "status": "recorded",
        "queue": "collection_shop_dashboard_dlx",
        "payload": payload,
    }


def _collect_one_day(
    runtime: ShopDashboardRuntimeConfig,
    metric_date: str,
    browser: BrowserScraper,
) -> dict[str, Any]:
    settings = get_settings().shop_dashboard
    lock_manager = LockManager()
    state_store = SessionStateStore(base_dir=Path(".runtime") / "shop_dashboard_state")
    login_state_manager = LoginStateManager(state_store=state_store)
    account_id = str(getattr(runtime, "account_id", "") or f"shop_{runtime.shop_id}")
    shop_lock_token = lock_manager.acquire_shop_lock(
        runtime.shop_id, ttl_seconds=settings.lock_ttl_seconds
    )
    if not shop_lock_token:
        return _build_expired_account_result(
            runtime,
            metric_date,
            reason="shop_locked",
        )

    scraper = HttpScraper(
        base_url=settings.base_url,
        timeout=float(runtime.timeout),
        graphql_query=runtime.graphql_query,
    )
    last_error: ScrapingFailedException | None = None
    try:
        for stage in runtime.fallback_chain:
            stage_name = str(stage).strip().lower()
            if stage_name == "http":
                try:
                    payload = scraper.fetch_dashboard_with_context(runtime, metric_date)
                    payload["source"] = "script"
                    return _normalize_task_result(runtime, metric_date, payload)
                except ScrapingFailedException as exc:
                    last_error = exc
                    continue
            if stage_name == "browser":
                account_lock_token: str | None = None
                try:
                    can_refresh = _run_async(
                        login_state_manager.check_and_refresh(account_id)
                    )
                    if not can_refresh:
                        return _build_expired_account_result(
                            runtime,
                            metric_date,
                            reason="login_expired",
                        )
                    account_lock_token = lock_manager.acquire_account_lock(
                        account_id,
                        ttl_seconds=settings.lock_ttl_seconds,
                    )
                    if not account_lock_token:
                        return _build_expired_account_result(
                            runtime,
                            metric_date,
                            reason="account_locked",
                        )
                    payload = browser.retry_http(scraper, runtime, metric_date)
                    state_cookies = state_store.load_cookie_mapping(account_id)
                    if state_cookies:
                        runtime.cookies = state_cookies
                    return _normalize_task_result(runtime, metric_date, payload)
                except ScrapingFailedException as exc:
                    last_error = exc
                    continue
                finally:
                    if account_lock_token:
                        lock_manager.release_account_lock(
                            account_id, account_lock_token
                        )
            if stage_name == "llm":
                return _build_llm_fallback_result(runtime, metric_date)
        if last_error is not None:
            raise last_error
        raise ScrapingFailedException(
            "Unsupported fallback chain",
            error_data={"fallback_chain": list(runtime.fallback_chain)},
        )
    finally:
        scraper.close()
        lock_manager.release_shop_lock(runtime.shop_id, shop_lock_token)


def _build_expired_account_result(
    runtime: ShopDashboardRuntimeConfig,
    metric_date: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "status": "degraded",
        "shop_id": runtime.shop_id,
        "metric_date": metric_date,
        "rule_id": runtime.rule_id,
        "execution_id": runtime.execution_id,
        "source": "degraded",
        "reason": reason,
        "total_score": 0.0,
        "product_score": 0.0,
        "logistics_score": 0.0,
        "service_score": 0.0,
        "reviews": {"summary": {}, "items": []},
        "violations": {"summary": {}, "waiting_list": []},
        "raw": {},
    }


def _normalize_task_result(
    runtime: ShopDashboardRuntimeConfig, metric_date: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return {
        "status": "success",
        "shop_id": runtime.shop_id,
        "metric_date": metric_date,
        "rule_id": runtime.rule_id,
        "execution_id": runtime.execution_id,
        "source": payload.get("source", "script"),
        "total_score": payload.get("total_score", 0.0),
        "product_score": payload.get("product_score", 0.0),
        "logistics_score": payload.get("logistics_score", 0.0),
        "service_score": payload.get("service_score", 0.0),
        "reviews": payload.get("reviews", {"summary": {}, "items": []}),
        "violations": payload.get("violations", {"summary": {}, "waiting_list": []}),
        "raw": payload.get("raw", {}),
    }


def _build_llm_fallback_result(
    runtime: ShopDashboardRuntimeConfig, metric_date: str
) -> dict[str, Any]:
    return {
        "status": "success",
        "shop_id": runtime.shop_id,
        "metric_date": metric_date,
        "rule_id": runtime.rule_id,
        "execution_id": runtime.execution_id,
        "source": "llm",
        "total_score": 0.0,
        "product_score": 0.0,
        "logistics_score": 0.0,
        "service_score": 0.0,
        "reviews": {"summary": {}, "items": []},
        "violations": {"summary": {}, "waiting_list": []},
        "raw": {},
    }


def _resolve_metric_dates(runtime: ShopDashboardRuntimeConfig) -> list[str]:
    if runtime.time_range:
        start = runtime.time_range.get("start")
        end = runtime.time_range.get("end")
        if isinstance(start, str) and isinstance(end, str):
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
            if end_date < start_date:
                start_date, end_date = end_date, start_date
            days = (end_date - start_date).days
            return [
                (start_date + timedelta(days=offset)).isoformat()
                for offset in range(days + 1)
            ]

    base_date = datetime.now(UTC).date() - timedelta(
        days=_parse_data_latency(runtime.data_latency)
    )
    if runtime.incremental_mode == "BY_DATE" and runtime.backfill_last_n_days > 0:
        return [
            (base_date - timedelta(days=offset)).isoformat()
            for offset in range(runtime.backfill_last_n_days)
        ]
    return [base_date.isoformat()]


def _parse_data_latency(data_latency: str) -> int:
    value = str(data_latency).strip().upper()
    if value.startswith("T+"):
        try:
            return max(int(value[2:]), 0)
        except ValueError:
            return 0
    return 0


def _build_business_key(runtime: ShopDashboardRuntimeConfig, metric_date: str) -> str:
    if runtime.dedupe_key:
        return runtime.dedupe_key.format(
            shop_id=runtime.shop_id,
            date=metric_date,
            rule_id=runtime.rule_id,
            execution_id=runtime.execution_id,
        )
    return f"{runtime.shop_id}:{metric_date}:{runtime.rule_id}"


async def _load_runtime_config(
    *,
    data_source_id: int,
    rule_id: int,
    execution_id: str,
) -> ShopDashboardRuntimeConfig:
    if async_session_factory is None:
        raise ScrapingFailedException("Database is not initialized")
    async with async_session_factory() as session:
        ds_repo = DataSourceRepository(session)
        rule_repo = ScrapingRuleRepository(session)
        data_source = await ds_repo.get_by_id(data_source_id)
        rule = await rule_repo.get_by_id(rule_id)
        if data_source is None or rule is None:
            raise ScrapingFailedException(
                "Data source or scraping rule not found",
                error_data={"data_source_id": data_source_id, "rule_id": rule_id},
            )
        if data_source.status != DataSourceStatus.ACTIVE:
            raise ScrapingFailedException(
                "Data source is inactive",
                error_data={"data_source_id": data_source_id},
            )
        if rule.status != ScrapingRuleStatus.ACTIVE:
            raise ScrapingFailedException(
                "Scraping rule is inactive",
                error_data={"rule_id": rule_id},
            )
        runtime = build_runtime_config(
            data_source=data_source, rule=rule, execution_id=execution_id
        )
        if not runtime.api_groups:
            raise ScrapingFailedException(
                "No API groups resolved for runtime",
                error_data={
                    "rule_id": rule_id,
                    "target_type": runtime.target_type,
                    "metrics": runtime.metrics,
                },
            )
        return runtime


async def _persist_result(
    runtime: ShopDashboardRuntimeConfig,
    metric_date: str,
    payload: dict[str, Any],
) -> None:
    if async_session_factory is None:
        return
    async with async_session_factory() as session:
        repo = ShopDashboardRepository(session)
        metric_day = date.fromisoformat(metric_date)
        await repo.upsert_score(
            shop_id=runtime.shop_id,
            metric_date=metric_day,
            total_score=float(payload.get("total_score", 0.0)),
            product_score=float(payload.get("product_score", 0.0)),
            logistics_score=float(payload.get("logistics_score", 0.0)),
            service_score=float(payload.get("service_score", 0.0)),
            source=str(payload.get("source", "script")),
        )

        reviews = payload.get("reviews", {}).get("items", [])
        review_rows = []
        for review in reviews:
            review_rows.append(
                {
                    "review_id": review.get("id") or review.get("review_id") or "",
                    "content": review.get("content") or "",
                    "is_replied": bool(review.get("shop_reply")),
                    "source": str(payload.get("source", "script")),
                }
            )
        await repo.replace_reviews(
            shop_id=runtime.shop_id,
            metric_date=metric_day,
            reviews=review_rows,
        )

        violations = payload.get("violations", {}).get("waiting_list", [])
        violation_rows = []
        for item in violations:
            violation_rows.append(
                {
                    "violation_id": item.get("ticket_id")
                    or item.get("id")
                    or item.get("rule")
                    or "",
                    "violation_type": item.get("type")
                    or item.get("rule_type")
                    or "unknown",
                    "description": item.get("description") or item.get("rule"),
                    "score": int(item.get("score") or 0),
                    "source": str(payload.get("source", "script")),
                }
            )
        await repo.replace_violations(
            shop_id=runtime.shop_id,
            metric_date=metric_day,
            violations=violation_rows,
        )
        await session.commit()


def _run_async(coro):
    return asyncio.run(coro)
