from __future__ import annotations

import logging
import threading
import time
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

from src.agents import LLMDashboardAgent
from src.cache import resolve_sync_redis_client
from src.config import get_settings
from src.domains.shop_dashboard.repository import ShopDashboardRepository
from src.scrapers.shop_dashboard.http_scraper import HttpScraper
from src.scrapers.shop_dashboard.lock_manager import LockManager
from src.scrapers.shop_dashboard.login_state_manager import LoginStateManager
from src.scrapers.shop_dashboard.exceptions import ShopDashboardScraperError
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore
from src.scrapers.shop_dashboard.shop_selection_validator import (
    normalize_shop_selection_payload,
)
from src.shared.payload_extractors import extract_nested_list
from src import session
from src.tasks.base import TaskStatusMixin, write_started_status_safe
from src.tasks.exceptions import ScrapingFailedException
from src.tasks.funboost_compat import boost, fct
from src.tasks.params import CollectionTaskParams

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


def _resolve_account_id(runtime: ShopDashboardRuntimeConfig) -> str:
    account_id = str(getattr(runtime, "account_id", "") or "").strip()
    if account_id:
        return account_id
    rule_id = int(getattr(runtime, "rule_id", 0) or 0)
    if rule_id > 0:
        return f"rule_{rule_id}"
    return f"shop_{runtime.shop_id}"


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
    started_at = write_started_status_safe(
        sync_shop_dashboard,
        "sync_shop_dashboard",
        triggered_by,
        logger=logger,
    )
    redis_client = resolve_sync_redis_client()
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
    runtime_overrides = normalize_shop_selection_payload(runtime_overrides)
    from src.application.collection.usecase import CollectionUseCase

    usecase = CollectionUseCase()
    result = usecase.execute(
        data_source_id=data_source_id,
        rule_id=rule_id,
        execution_id=execution_id,
        queue_task_id=str(getattr(fct, "task_id", "") or ""),
        started_at=started_at,
        triggered_by=triggered_by,
        overrides=runtime_overrides,
        redis_client=redis_client,
    )
    items = result.get("items")
    unsupported = False
    if isinstance(items, list):
        if "processed_rows" not in result:
            result["processed_rows"] = len(items)
        unsupported = any(
            isinstance(item, Mapping)
            and str(item.get("reason", "")).strip() == "account_shop_switch_unsupported"
            for item in items
        )
    if unsupported:
        result["recommended_collection_mode"] = "per_shop_account"
    return result


@boost(
    CollectionTaskParams(
        queue_name="collection_shop_dashboard_dlx",
        consumer_override_cls=TaskStatusMixin,
    )
)
def handle_collection_shop_dashboard_dead_letter(**payload) -> dict[str, Any]:
    logger.warning(
        "dead letter received: queue=collection_shop_dashboard_dlx payload=%r",
        payload,
    )
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

    account_id = _resolve_account_id(runtime)

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
    *,
    lock_manager: LockManager | None = None,
    state_store: SessionStateStore | None = None,
    login_state_manager: LoginStateManager | None = None,
) -> dict[str, Any]:
    settings = get_settings().shop_dashboard
    lock_manager = lock_manager or LockManager()
    account_id = _resolve_account_id(runtime)
    shop_lock_id = _resolve_shop_lock_id(runtime.shop_id, account_id)
    last_error: Exception | None = None
    http_error: Exception | None = None
    retry_count = 0
    fallback_trace: list[dict[str, Any]] = []
    with _acquire_shop_lock(
        lock_manager,
        shop_lock_id,
        settings.shop_lock_ttl_seconds,
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
                if stage_name == "agent":
                    return _build_agent_fallback_result(
                        runtime,
                        metric_date,
                        http_error=http_error,
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


def _build_expired_account_result(
    runtime: ShopDashboardRuntimeConfig,
    metric_date: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "status": "degraded",
        "shop_id": runtime.shop_id,
        "target_shop_id": runtime.shop_id,
        "actual_shop_id": runtime.shop_id,
        "mismatch_status": "matched",
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
    target_shop_id = str(runtime.shop_id or "").strip()
    actual_shop_id = str(
        payload.get("actual_shop_id") or payload.get("shop_id") or target_shop_id
    ).strip()
    normalized_status = str(payload.get("status") or "success").strip() or "success"
    result = {
        "status": normalized_status,
        "shop_id": runtime.shop_id,
        "target_shop_id": target_shop_id,
        "actual_shop_id": actual_shop_id,
        "mismatch_status": (
            "matched" if actual_shop_id == target_shop_id else "mismatched"
        ),
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
    shop_name = str(payload.get("shop_name", "")).strip()
    if shop_name:
        result["shop_name"] = shop_name
    if "reason" in payload:
        result["reason"] = payload.get("reason")
    for key in ("violations_detail", "arbitration_detail", "dsr_trend"):
        if key in payload:
            result[key] = payload.get(key)
    if not isinstance(result["raw"], dict):
        result["raw"] = {}
    return result


def _resolve_agent_reason(http_error: Exception | None) -> str:
    if http_error is not None:
        return "http_failed"
    return "fallback"


def _build_agent_fallback_result(
    runtime: ShopDashboardRuntimeConfig,
    metric_date: str,
    *,
    http_error: Exception | None = None,
    retry_count: int = 0,
    fallback_trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    reason = _resolve_agent_reason(http_error)
    payload: dict[str, Any] = {
        "status": "success",
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
    llm_error: Exception | None = None
    try:
        patched = agent.supplement_cold_data(
            payload,
            runtime.shop_id,
            metric_date,
            reason=reason,
        )
    except Exception as exc:
        patched = None
        llm_error = exc
    finally:
        close = getattr(agent, "close", None)
        if callable(close):
            close()

    if not isinstance(patched, dict):
        failure_error = (
            str(llm_error) if llm_error is not None else "invalid_llm_payload"
        )
        raw = dict(payload.get("raw") or {})
        raw["llm_patch"] = {
            "status": "failed",
            "reason": reason,
            "error": failure_error,
        }
        payload["raw"] = raw
        payload["status"] = "degraded"
        payload["reason"] = "llm_failed"
        patched = payload
        _append_fallback_trace(
            fallback_trace if isinstance(fallback_trace, list) else [],
            stage="agent",
            status="failed",
            error=llm_error if llm_error is not None else RuntimeError(failure_error),
        )
    else:
        _append_fallback_trace(
            fallback_trace if isinstance(fallback_trace, list) else [],
            stage="agent",
            status="success",
        )

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
            logger.warning("unrecognized data_latency format: %r", data_latency)
            return 0
    if value:
        logger.warning("unrecognized data_latency format: %r", data_latency)
    return 0


def _resolve_shop_lock_id(shop_id: str, account_id: str) -> str:
    normalized_shop_id = str(shop_id or "").strip()
    if normalized_shop_id:
        return normalized_shop_id
    normalized_account_id = str(account_id or "").strip()
    if normalized_account_id:
        return f"account:{normalized_account_id}"
    return "account:anonymous"


class _SafeFormatContext(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _safe_format_business_key(template: str, context: dict[str, Any]) -> str:
    try:
        return template.format_map(_SafeFormatContext(context))
    except Exception:
        return template


def _build_business_key(
    runtime: ShopDashboardRuntimeConfig,
    metric_date: str,
    *,
    plan_unit: Any | None = None,
    queue_task_id: str | None = None,
) -> str:
    window_start = getattr(plan_unit, "window_start", None)
    window_end = getattr(plan_unit, "window_end", None)
    granular = getattr(plan_unit, "granularity", runtime.granularity)
    normalized_queue_task_id = str(queue_task_id or "").strip()
    format_context = {
        "shop_id": runtime.shop_id,
        "date": metric_date,
        "metric_date": metric_date,
        "rule_id": runtime.rule_id,
        "execution_id": runtime.execution_id,
        "queue_task_id": normalized_queue_task_id,
        "granularity": granular,
        "window_start": window_start.isoformat() if window_start else "",
        "window_end": window_end.isoformat() if window_end else "",
    }
    if runtime.dedupe_key:
        business_key = _safe_format_business_key(runtime.dedupe_key, format_context)
        if normalized_queue_task_id and "{queue_task_id}" not in runtime.dedupe_key:
            return f"{business_key}:{normalized_queue_task_id}"
        return business_key
    base_key = (
        f"{runtime.shop_id}:{metric_date}:{runtime.rule_id}:{runtime.execution_id}"
    )
    if normalized_queue_task_id:
        return f"{base_key}:{normalized_queue_task_id}"
    return base_key


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
        metric_day_text = metric_day.isoformat()
        runtime_shop_id = _normalize_shop_id(runtime.shop_id)
        actual_shop_id = _normalize_shop_id(
            payload.get("actual_shop_id") or payload.get("shop_id") or runtime_shop_id
        )
        target_shop_id = _normalize_shop_id(
            payload.get("target_shop_id") or runtime_shop_id
        )
        resolved_shop_id = actual_shop_id or runtime_shop_id
        if not resolved_shop_id or not target_shop_id:
            logger.warning(
                "skip dashboard persistence due to empty shop key: target_shop_id=%s actual_shop_id=%s resolved_shop_id=%s metric_date=%s",
                target_shop_id,
                actual_shop_id,
                resolved_shop_id,
                metric_day_text,
            )
            return
        if actual_shop_id != target_shop_id:
            logger.warning(
                "skip dashboard persistence due to shop mismatch: target_shop_id=%s actual_shop_id=%s resolved_shop_id=%s metric_date=%s",
                target_shop_id,
                actual_shop_id,
                resolved_shop_id,
                metric_day_text,
            )
            return
        source = str(payload.get("source", "script"))
        await repo.upsert_score(
            shop_id=resolved_shop_id,
            metric_date=metric_day,
            total_score=float(payload.get("total_score", 0.0)),
            product_score=float(payload.get("product_score", 0.0)),
            logistics_score=float(payload.get("logistics_score", 0.0)),
            service_score=float(payload.get("service_score", 0.0)),
            bad_behavior_score=float(payload.get("bad_behavior_score", 0.0)),
            shop_name=str(payload.get("shop_name", "")).strip() or None,
            source=source,
        )

        reviews = payload.get("reviews", {}).get("items", [])
        review_rows = []
        for review in reviews:
            review_rows.append(
                {
                    "review_id": review.get("id") or review.get("review_id") or "",
                    "content": review.get("content") or "",
                    "is_replied": bool(review.get("shop_reply")),
                    "source": source,
                }
            )
        await repo.replace_reviews(
            shop_id=resolved_shop_id,
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
                    "source": source,
                }
            )
        await repo.replace_violations(
            shop_id=resolved_shop_id,
            metric_date=metric_day,
            violations=violation_rows,
        )
        await db_session.commit()


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
            extracted = extract_nested_list(raw_violations.get("waiting_list"))
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


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _normalize_shop_id(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if normalized.isdigit():
        return str(int(normalized))
    return normalized
