from __future__ import annotations

import inspect
import logging
import threading
import time
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from src.agents import LLMDashboardAgent
from src.config import get_settings
from src.domains.data_source.enums import DataSourceStatus, ScrapingRuleStatus
from src.domains.data_source.repository import DataSourceRepository
from src.domains.scraping_rule.repository import ScrapingRuleRepository
from src.domains.shop_dashboard.repository import ShopDashboardRepository
from src.scrapers.shop_dashboard.browser_scraper import BrowserScraper
from src.scrapers.shop_dashboard.http_scraper import HttpScraper
from src.scrapers.shop_dashboard.lock_manager import LockManager
from src.scrapers.shop_dashboard.login_state_manager import LoginStateManager
from src.scrapers.shop_dashboard.exceptions import ShopDashboardScraperError
from src.scrapers.shop_dashboard.runtime import (
    ShopDashboardRuntimeConfig,
    build_runtime_config,
)
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore
from src import session
from src.tasks.base import TaskStatusMixin
from src.tasks.exceptions import ScrapingFailedException
from src.tasks.funboost_compat import boost, fct
from src.tasks.params import CollectionTaskParams
from src.tasks.status_store import write_started_task_status

logger = logging.getLogger(__name__)


class _RateLimiter:
    def __init__(self, policy: int | dict[str, Any] | None):
        self._qps = 0.0
        self._burst = 1.0
        self._tokens = 1.0
        self._last_refill = time.perf_counter()
        self._lock = threading.Lock()
        self._configure(policy)

    def _configure(self, policy: int | dict[str, Any] | None) -> None:
        if isinstance(policy, int):
            self._qps = max(float(policy), 0.0)
            self._burst = 1.0
        elif isinstance(policy, dict):
            raw_qps = policy.get("qps", 0)
            raw_burst = policy.get("burst", 1)
            self._qps = max(float(raw_qps or 0), 0.0)
            self._burst = max(float(raw_burst or 1), 1.0)
        self._tokens = self._burst

    def wait(self) -> None:
        if self._qps <= 0:
            return
        while True:
            sleep_seconds = 0.0
            with self._lock:
                now = time.perf_counter()
                elapsed = max(now - self._last_refill, 0.0)
                self._tokens = min(self._burst, self._tokens + elapsed * self._qps)
                self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                sleep_seconds = (1.0 - self._tokens) / self._qps
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)


def _write_started_status(
    task_func,
    task_name: str,
    triggered_by: int | None,
    execution_id: int | None = None,
) -> None:
    try:
        task_id = str(getattr(fct, "task_id", "unknown"))
        write_started_task_status(
            owner=task_func,
            task_id=task_id,
            task_name=task_name,
            triggered_by=triggered_by,
            execution_id=execution_id,
        )
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
    shop_id: str | None = None,
    shop_ids: list[str] | str | None = None,
    all: bool | None = None,
    granularity: str | None = None,
    timezone: str | None = None,
    time_range: dict[str, Any] | None = None,
    incremental_mode: str | None = None,
    backfill_last_n_days: int | None = None,
    data_latency: str | None = None,
    filters: dict[str, Any] | None = None,
    dimensions: list[str] | None = None,
    metrics: list[str] | None = None,
    dedupe_key: str | None = None,
    rate_limit: int | dict[str, Any] | None = None,
    top_n: int | None = None,
    sort_by: str | None = None,
    include_long_tail: bool | None = None,
    session_level: bool | None = None,
    extra_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _write_started_status(sync_shop_dashboard, "sync_shop_dashboard", triggered_by)
    redis_client = sync_shop_dashboard.publisher.redis_db_frame
    runtime_overrides = {
        key: value
        for key, value in {
            "shop_id": shop_id,
            "shop_ids": shop_ids,
            "all": all,
            "granularity": granularity,
            "timezone": timezone,
            "time_range": time_range,
            "incremental_mode": incremental_mode,
            "backfill_last_n_days": backfill_last_n_days,
            "data_latency": data_latency,
            "filters": filters,
            "dimensions": dimensions,
            "metrics": metrics,
            "dedupe_key": dedupe_key,
            "rate_limit": rate_limit,
            "top_n": top_n,
            "sort_by": sort_by,
            "include_long_tail": include_long_tail,
            "session_level": session_level,
            "extra_config": extra_config,
        }.items()
        if value is not None
    }
    from src.application.collection.usecase import CollectionUseCase

    usecase = CollectionUseCase()
    return usecase.execute(
        data_source_id=data_source_id,
        rule_id=rule_id,
        execution_id=execution_id,
        queue_task_id=str(getattr(fct, "task_id", "") or ""),
        triggered_by=triggered_by,
        overrides=runtime_overrides,
        redis_client=redis_client,
    )


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


def _materialize_runtime_storage_state(
    runtime: ShopDashboardRuntimeConfig,
    state_store: SessionStateStore,
) -> ShopDashboardRuntimeConfig:
    storage_state = getattr(runtime, "storage_state", None)
    if not isinstance(storage_state, dict):
        return runtime

    account_id = str(getattr(runtime, "account_id", "") or "").strip()
    if not account_id:
        account_id = f"shop_{runtime.shop_id}"

    state_store.save(account_id, storage_state)
    cookies = state_store.load_cookie_mapping(account_id)
    if cookies:
        return replace(runtime, cookies=dict(cookies))
    return runtime


@contextmanager
def _acquire_shop_lock(
    lock_manager: LockManager,
    shop_lock_id: str,
    ttl_seconds: int,
) -> Generator[str | None, None, None]:
    token = lock_manager.acquire_shop_lock(shop_lock_id, ttl_seconds=ttl_seconds)
    try:
        yield token
    finally:
        if token:
            lock_manager.release_shop_lock(shop_lock_id, token)


@contextmanager
def _acquire_account_lock(
    lock_manager: LockManager,
    account_id: str,
    ttl_seconds: int,
) -> Generator[str | None, None, None]:
    token = lock_manager.acquire_account_lock(account_id, ttl_seconds=ttl_seconds)
    try:
        yield token
    finally:
        if token:
            lock_manager.release_account_lock(account_id, token)


def _normalize_fallback_stage(stage: Any) -> str:
    stage_name = str(stage).strip().lower()
    if stage_name in {"agent", "llm"}:
        return "agent"
    return stage_name


def _append_fallback_trace(
    fallback_trace: list[dict[str, Any]],
    *,
    stage: str,
    status: str,
    error: Exception | None = None,
) -> None:
    entry: dict[str, Any] = {"stage": stage, "status": status}
    if error is not None:
        entry["error"] = str(error)
    fallback_trace.append(entry)


def _collect_one_day(
    runtime: ShopDashboardRuntimeConfig,
    metric_date: str,
    browser: BrowserScraper,
    *,
    lock_manager: LockManager | None = None,
    state_store: SessionStateStore | None = None,
    login_state_manager: LoginStateManager | None = None,
) -> dict[str, Any]:
    settings = get_settings().shop_dashboard
    lock_manager = lock_manager or LockManager()
    state_store = state_store or SessionStateStore(
        base_dir=Path(".runtime") / "shop_dashboard_state"
    )
    login_state_manager = login_state_manager or LoginStateManager(
        state_store=state_store
    )
    explicit_account_id = str(getattr(runtime, "account_id", "") or "").strip()
    account_id = explicit_account_id or f"shop_{runtime.shop_id}"
    shop_lock_id = _resolve_shop_lock_id(runtime.shop_id, account_id)
    last_error: Exception | None = None
    http_error: Exception | None = None
    browser_error: Exception | None = None
    retry_count = 0
    fallback_trace: list[dict[str, Any]] = []
    with _acquire_shop_lock(
        lock_manager,
        shop_lock_id,
        settings.lock_ttl_seconds,
    ) as shop_lock_token:
        if not shop_lock_token:
            return _build_expired_account_result(
                runtime,
                metric_date,
                reason="shop_locked",
            )
        with HttpScraper(
            base_url=settings.base_url,
            timeout=float(runtime.timeout),
            graphql_query=runtime.graphql_query,
        ) as scraper:
            for stage in runtime.fallback_chain:
                stage_name = _normalize_fallback_stage(stage)
                if stage_name == "http":
                    try:
                        payload = scraper.fetch_dashboard_with_context(
                            runtime, metric_date
                        )
                        payload["source"] = "script"
                        _append_fallback_trace(
                            fallback_trace,
                            stage="http",
                            status="success",
                        )
                        return _normalize_task_result(
                            runtime,
                            metric_date,
                            payload,
                            retry_count=retry_count,
                            fallback_trace=fallback_trace,
                        )
                    except (ScrapingFailedException, ShopDashboardScraperError) as exc:
                        retry_count += 1
                        last_error = exc
                        http_error = exc
                        _append_fallback_trace(
                            fallback_trace,
                            stage="http",
                            status="failed",
                            error=exc,
                        )
                        continue
                if stage_name == "browser":
                    try:
                        with _acquire_account_lock(
                            lock_manager,
                            account_id,
                            settings.lock_ttl_seconds,
                        ) as account_lock_token:
                            if not account_lock_token:
                                return _build_expired_account_result(
                                    runtime,
                                    metric_date,
                                    reason="account_locked",
                                )
                            if explicit_account_id:
                                can_refresh = _run_async(
                                    login_state_manager.check_and_refresh(account_id)
                                )
                                if not can_refresh:
                                    return _build_expired_account_result(
                                        runtime,
                                        metric_date,
                                        reason="login_expired",
                                    )
                                state_cookies = state_store.load_cookie_mapping(
                                    account_id
                                )
                                if state_cookies:
                                    runtime.cookies = state_cookies
                            payload = browser.retry_http(scraper, runtime, metric_date)
                            _append_fallback_trace(
                                fallback_trace,
                                stage="browser",
                                status="success",
                            )
                            return _normalize_task_result(
                                runtime,
                                metric_date,
                                payload,
                                retry_count=retry_count,
                                fallback_trace=fallback_trace,
                            )
                    except (ScrapingFailedException, ShopDashboardScraperError) as exc:
                        retry_count += 1
                        last_error = exc
                        browser_error = exc
                        _append_fallback_trace(
                            fallback_trace,
                            stage="browser",
                            status="failed",
                            error=exc,
                        )
                        if _is_login_expired_exception(exc):
                            _run_async(
                                login_state_manager.mark_expired(
                                    account_id,
                                    reason="refresh_failed",
                                )
                            )
                            return _build_expired_account_result(
                                runtime,
                                metric_date,
                                reason="login_expired",
                            )
                        continue
                if stage_name == "agent":
                    _append_fallback_trace(
                        fallback_trace,
                        stage="agent",
                        status="success",
                    )
                    return _build_agent_fallback_result(
                        runtime,
                        metric_date,
                        http_error=http_error,
                        browser_error=browser_error,
                        retry_count=retry_count,
                        fallback_trace=fallback_trace,
                    )

            if last_error is not None:
                raise last_error
            raise ScrapingFailedException(
                "Unsupported fallback chain",
                error_data={
                    "fallback_chain": [
                        _normalize_fallback_stage(stage)
                        for stage in runtime.fallback_chain
                    ]
                },
            )


def _is_login_expired_exception(exc: Exception) -> bool:
    error_data = getattr(exc, "error_data", {})
    if isinstance(error_data, dict):
        reason = str(error_data.get("reason", "")).strip().lower()
        if "expired" in reason:
            return True

    message = str(exc).strip().lower()
    return "expired" in message and any(
        token in message for token in ("login", "session", "cookie")
    )


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
        "bad_behavior_score": 0.0,
        "reviews": {"summary": {}, "items": []},
        "violations": {"summary": {}, "waiting_list": []},
        "raw": {},
    }


def _normalize_task_result(
    runtime: ShopDashboardRuntimeConfig,
    metric_date: str,
    payload: dict[str, Any],
    retry_count: int = 0,
    fallback_trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = {
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
        "bad_behavior_score": payload.get("bad_behavior_score", 0.0),
        "reviews": payload.get("reviews", {"summary": {}, "items": []}),
        "violations": payload.get("violations", {"summary": {}, "waiting_list": []}),
        "raw": payload.get("raw", {}),
        "retry_count": retry_count,
        "fallback_trace": list(fallback_trace or []),
    }
    for key in ("violations_detail", "arbitration_detail", "dsr_trend"):
        if key in payload:
            result[key] = payload.get(key)
    if not isinstance(result["raw"], dict):
        result["raw"] = {}
    return result


def _resolve_agent_reason(
    http_error: Exception | None,
    browser_error: Exception | None,
) -> str:
    if http_error is not None and browser_error is not None:
        return "http_browser_failed"
    if http_error is not None:
        return "http_failed"
    if browser_error is not None:
        return "browser_failed"
    return "fallback"


def _build_agent_fallback_result(
    runtime: ShopDashboardRuntimeConfig,
    metric_date: str,
    *,
    http_error: Exception | None = None,
    browser_error: Exception | None = None,
    retry_count: int = 0,
    fallback_trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    reason = _resolve_agent_reason(http_error, browser_error)
    payload: dict[str, Any] = {
        "source": "llm",
        "total_score": 0.0,
        "product_score": 0.0,
        "logistics_score": 0.0,
        "service_score": 0.0,
        "bad_behavior_score": 0.0,
        "reviews": {"summary": {}, "items": []},
        "violations": {"summary": {}, "waiting_list": []},
        "raw": {},
    }

    agent = LLMDashboardAgent()
    try:
        patched = agent.supplement_cold_data(
            payload,
            runtime.shop_id,
            metric_date,
            reason=reason,
        )
    except Exception as exc:
        raw = dict(payload.get("raw") or {})
        raw["llm_patch"] = {
            "status": "failed",
            "reason": reason,
            "error": str(exc),
        }
        payload["raw"] = raw
        patched = payload
    finally:
        close = getattr(agent, "close", None)
        if callable(close):
            close()

    if not isinstance(patched, dict):
        patched = payload
    patched["source"] = "llm"
    raw = patched.get("raw")
    if not isinstance(raw, dict):
        raw = {}
    raw.setdefault("llm_patch", {"status": "success", "reason": reason})
    patched["raw"] = raw
    return _normalize_task_result(
        runtime,
        metric_date,
        patched,
        retry_count=retry_count,
        fallback_trace=fallback_trace,
    )


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


def _resolve_shop_lock_id(shop_id: str, account_id: str) -> str:
    normalized_shop_id = str(shop_id or "").strip()
    if normalized_shop_id:
        return normalized_shop_id
    normalized_account_id = str(account_id or "").strip()
    if normalized_account_id:
        return f"account:{normalized_account_id}"
    return "account:anonymous"


def _is_result_cache_enabled(execution_id: str) -> bool:
    return not execution_id.startswith("cron_cookie_health_check_")


def _build_business_key(
    runtime: ShopDashboardRuntimeConfig,
    metric_date: str,
    *,
    plan_unit: Any | None = None,
) -> str:
    window_start = getattr(plan_unit, "window_start", None)
    window_end = getattr(plan_unit, "window_end", None)
    granular = getattr(plan_unit, "granularity", runtime.granularity)
    format_context = {
        "shop_id": runtime.shop_id,
        "date": metric_date,
        "metric_date": metric_date,
        "rule_id": runtime.rule_id,
        "execution_id": runtime.execution_id,
        "granularity": granular,
        "window_start": window_start.isoformat() if window_start else "",
        "window_end": window_end.isoformat() if window_end else "",
    }
    if runtime.dedupe_key:
        try:
            return runtime.dedupe_key.format(**format_context)
        except KeyError:
            return runtime.dedupe_key.format(
                shop_id=runtime.shop_id,
                date=metric_date,
                rule_id=runtime.rule_id,
                execution_id=runtime.execution_id,
            )
    return f"{runtime.shop_id}:{metric_date}:{runtime.rule_id}:{runtime.execution_id}"


async def _load_runtime_config(
    *,
    data_source_id: int,
    rule_id: int,
    execution_id: str,
    overrides: Mapping[str, Any] | None = None,
) -> ShopDashboardRuntimeConfig:
    session_factory = session.async_session_factory
    if session_factory is None:
        raise ScrapingFailedException("Database is not initialized")
    async with session_factory() as db_session:
        ds_repo = DataSourceRepository(db_session)
        rule_repo = ScrapingRuleRepository(db_session)
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
            data_source=data_source,
            rule=rule,
            execution_id=execution_id,
            overrides=dict(overrides or {}),
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
    session_factory = session.async_session_factory
    if session_factory is None:
        return
    async with session_factory() as db_session:
        repo = ShopDashboardRepository(db_session)
        metric_day = date.fromisoformat(metric_date)
        await repo.upsert_score(
            shop_id=runtime.shop_id,
            metric_date=metric_day,
            total_score=float(payload.get("total_score", 0.0)),
            product_score=float(payload.get("product_score", 0.0)),
            logistics_score=float(payload.get("logistics_score", 0.0)),
            service_score=float(payload.get("service_score", 0.0)),
            bad_behavior_score=float(payload.get("bad_behavior_score", 0.0)),
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

        violations = _extract_violation_items(payload)
        violation_rows = []
        for item in violations:
            violation_rows.append(
                {
                    "violation_id": item.get("ticket_id")
                    or item.get("ticketId")
                    or item.get("id")
                    or item.get("rule_id")
                    or item.get("penalty_id")
                    or item.get("rule")
                    or "",
                    "violation_type": item.get("type")
                    or item.get("rule_type")
                    or item.get("violation_type")
                    or item.get("penalty_type")
                    or "unknown",
                    "description": item.get("description")
                    or item.get("reason")
                    or item.get("rule"),
                    "score": _to_int(
                        item.get("score")
                        or item.get("deduct_score")
                        or item.get("deductScore")
                        or item.get("point")
                        or item.get("points")
                        or 0
                    ),
                    "source": str(payload.get("source", "script")),
                }
            )
        await repo.replace_violations(
            shop_id=runtime.shop_id,
            metric_date=metric_day,
            violations=violation_rows,
        )
        await db_session.commit()


def _run_async(coro):
    return session.run_coro(coro)


def _extract_violation_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    violations = payload.get("violations")
    if isinstance(violations, dict):
        direct = _normalize_violation_items(violations.get("waiting_list"))
        if direct:
            return direct

    raw = payload.get("raw")
    if isinstance(raw, dict):
        raw_violations = raw.get("violations")
        if isinstance(raw_violations, dict):
            extracted = _extract_list(raw_violations.get("waiting_list"))
            fallback = _normalize_violation_items(extracted)
            if fallback:
                return fallback

    return []


def _normalize_violation_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, Mapping):
            rows.append(dict(item))
    return rows


def _extract_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, Mapping):
        return []

    for key in ("list", "items", "records", "waiting_list", "rows", "result", "data"):
        nested = value.get(key)
        if isinstance(nested, list):
            return nested

    for key in ("data", "result", "records"):
        nested = value.get(key)
        if isinstance(nested, Mapping):
            extracted = _extract_list(nested)
            if extracted:
                return extracted

    return []


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _supports_shared_helpers(collector: Any) -> bool:
    try:
        signature = inspect.signature(collector)
    except (TypeError, ValueError):
        return True

    parameters = signature.parameters
    if any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    ):
        return True
    required = {"lock_manager", "state_store", "login_state_manager"}
    return required.issubset(parameters.keys())


collect_one_day = _collect_one_day
RateLimiter = _RateLimiter
build_business_key = _build_business_key
materialize_runtime_storage_state = _materialize_runtime_storage_state
