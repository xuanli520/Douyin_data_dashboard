from __future__ import annotations

import inspect
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from typing import Mapping

from sqlalchemy.exc import IntegrityError

from src import session
from src.application.collection.plan_builder import CollectionPlanBuilder
from src.application.collection.result_persister import CollectionResultPersister
from src.application.collection.runtime_loader import CollectionRuntimeLoader
from src.application.collection.runtime_loader import LoadedCollectionRuntime
from src.application.collection.shop_switch_capability import (
    ShopSwitchCapabilityService,
)
from src.cache import resolve_sync_redis_client
from src.config import get_settings
from src.domains.task.exceptions import ScrapingFailedException
from src.domains.task.exceptions import ShopDashboardNoTargetShopsException
from src.domains.task.exceptions import ShopDashboardCookieExpiredException
from src.domains.task.exceptions import ShopDashboardDataIncompleteException
from src.domains.task.exceptions import ShopDashboardShopCircuitBreakException
from src.domains.task.exceptions import ShopDashboardShopMismatchException
from src.domains.task.enums import TaskExecutionStatus
from src.domains.task.enums import TaskTriggerMode
from src.domains.task.enums import TaskType
from src.domains.scraping_rule.repository import ScrapingRuleRepository
from src.domains.task.repository import TaskDefinitionRepository
from src.domains.task.repository import TaskExecutionRepository
from src.middleware.monitor import observe_shop_dashboard_account_switch_unsupported
from src.middleware.monitor import observe_shop_dashboard_bootstrap_verify_failed
from src.middleware.monitor import observe_shop_dashboard_collection
from src.scrapers.shop_dashboard.browser_scraper import BrowserScraper
from src.scrapers.shop_dashboard.exceptions import DataIncompleteError
from src.scrapers.shop_dashboard.exceptions import LoginExpiredError
from src.scrapers.shop_dashboard.exceptions import ShopDashboardScraperError
from src.scrapers.shop_dashboard.lock_manager import LockManager
from src.scrapers.shop_dashboard.login_state_manager import LoginStateManager
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.scrapers.shop_dashboard.session_bootstrapper import SessionBootstrapper
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore
from src.shared.redis_keys import redis_keys
from src.shared.idempotency import FunboostIdempotencyHelper


class CollectionUseCase:
    def __init__(
        self,
        *,
        runtime_loader: CollectionRuntimeLoader | None = None,
        plan_builder: CollectionPlanBuilder | None = None,
        result_persister: CollectionResultPersister | None = None,
    ) -> None:
        self.runtime_loader = runtime_loader or CollectionRuntimeLoader()
        self.plan_builder = plan_builder or CollectionPlanBuilder()
        self.result_persister = result_persister or CollectionResultPersister()

    def execute(
        self,
        *,
        data_source_id: int,
        rule_id: int,
        execution_id: str,
        queue_task_id: str,
        triggered_by: int | None = None,
        overrides: Mapping[str, Any] | None = None,
        redis_client: Any | None = None,
    ) -> dict[str, Any]:
        return session.run_coro(
            self._execute_async(
                data_source_id=data_source_id,
                rule_id=rule_id,
                execution_id=execution_id,
                queue_task_id=queue_task_id,
                triggered_by=triggered_by,
                overrides=dict(overrides or {}),
                redis_client=redis_client,
            )
        )

    async def _execute_async(
        self,
        *,
        data_source_id: int,
        rule_id: int,
        execution_id: str,
        queue_task_id: str,
        triggered_by: int | None,
        overrides: dict[str, Any],
        redis_client: Any | None,
    ) -> dict[str, Any]:
        session_factory = session.async_session_factory
        if session_factory is None:
            raise ScrapingFailedException("Database is not initialized")

        idempotency_key = self._build_idempotency_key(
            data_source_id=data_source_id,
            rule_id=rule_id,
            execution_id=execution_id,
            queue_task_id=queue_task_id,
        )
        execution = await self._create_or_get_execution(
            data_source_id=data_source_id,
            rule_id=rule_id,
            execution_id=execution_id,
            queue_task_id=queue_task_id,
            triggered_by=triggered_by,
            overrides=overrides,
            idempotency_key=idempotency_key,
        )
        reused_result = self._resolve_reused_result(execution)
        if reused_result is not None:
            reused_result["reused"] = True
            return reused_result

        loaded_runtime: LoadedCollectionRuntime | None = None
        try:
            loaded_runtime = await self._load_runtime(
                data_source_id=data_source_id,
                rule_id=rule_id,
                execution_id=execution_id,
                overrides=overrides,
            )
            await self._mark_running(
                execution_id=execution.id if execution.id is not None else 0,
                rule_version=loaded_runtime.rule_version,
                effective_config_snapshot=loaded_runtime.effective_config_snapshot,
            )
            result = await self._collect_and_persist(
                runtime=loaded_runtime.runtime,
                data_source_id=data_source_id,
                rule_id=rule_id,
                execution_id=execution_id,
                queue_task_id=queue_task_id,
                redis_client=redis_client,
                session_factory=session_factory,
            )
            self._raise_when_all_units_failed(result)
            await self._mark_success(
                execution_id=execution.id if execution.id is not None else 0,
                rule_id=rule_id,
                rule_execution_id=execution_id,
                processed_rows=len(result["items"]),
                result=result,
            )
            return result
        except Exception as exc:
            mapped = self._map_scraper_exception(exc)
            await self._mark_failed(
                execution_id=execution.id if execution.id is not None else 0,
                error_message=str(mapped),
            )
            raise mapped

    async def _create_or_get_execution(
        self,
        *,
        data_source_id: int,
        rule_id: int,
        execution_id: str,
        queue_task_id: str,
        triggered_by: int | None,
        overrides: dict[str, Any],
        idempotency_key: str,
    ):
        session_factory = session.async_session_factory
        if session_factory is None:
            raise ScrapingFailedException("Database is not initialized")
        async with session_factory() as db_session:
            execution_repo = TaskExecutionRepository(db_session)
            existing_by_queue = None
            if queue_task_id:
                existing_by_queue = await execution_repo.get_by_queue_task_id(
                    queue_task_id
                )
            if existing_by_queue is not None:
                execution = await execution_repo.update(
                    existing_by_queue,
                    {
                        "idempotency_key": idempotency_key,
                        "payload": {
                            "data_source_id": data_source_id,
                            "rule_id": rule_id,
                            "execution_id": execution_id,
                            "overrides": dict(overrides),
                        },
                        "queue_task_id": queue_task_id,
                    },
                )
                await db_session.commit()
                return execution

            task_repo = TaskDefinitionRepository(db_session)
            task = await task_repo.get_by_task_type(TaskType.SHOP_DASHBOARD_COLLECTION)
            if task is None:
                task = await task_repo.create(
                    {
                        "name": "shop_dashboard_collection",
                        "task_type": TaskType.SHOP_DASHBOARD_COLLECTION,
                    }
                )
                await db_session.commit()

            trigger_mode = (
                TaskTriggerMode.SYSTEM
                if triggered_by is None
                else TaskTriggerMode.MANUAL
            )
            payload = {
                "data_source_id": data_source_id,
                "rule_id": rule_id,
                "execution_id": execution_id,
                "overrides": dict(overrides),
            }
            execution_data = {
                "task_id": task.id if task.id is not None else 0,
                "queue_task_id": queue_task_id or None,
                "status": TaskExecutionStatus.QUEUED,
                "trigger_mode": trigger_mode,
                "payload": payload,
                "triggered_by": triggered_by,
                "idempotency_key": idempotency_key,
                "effective_config_snapshot": {
                    "data_source_id": data_source_id,
                    "rule_id": rule_id,
                    "execution_id": execution_id,
                    "overrides": dict(overrides),
                },
            }
            try:
                execution = await execution_repo.create(execution_data)
                await db_session.commit()
                return execution
            except IntegrityError:
                await db_session.rollback()
                existing = await execution_repo.get_by_idempotency_key(idempotency_key)
                if existing is None:
                    raise
                if queue_task_id and existing.queue_task_id != queue_task_id:
                    try:
                        existing = await execution_repo.update(
                            existing,
                            {
                                "queue_task_id": queue_task_id,
                                "payload": payload,
                            },
                        )
                        await db_session.commit()
                    except IntegrityError:
                        await db_session.rollback()
                return existing

    async def _load_runtime(
        self,
        *,
        data_source_id: int,
        rule_id: int,
        execution_id: str,
        overrides: dict[str, Any],
    ) -> LoadedCollectionRuntime:
        session_factory = session.async_session_factory
        if session_factory is None:
            raise ScrapingFailedException("Database is not initialized")
        async with session_factory() as db_session:
            return await self.runtime_loader.load(
                session=db_session,
                data_source_id=data_source_id,
                rule_id=rule_id,
                execution_id=execution_id,
                overrides=overrides,
            )

    async def _mark_running(
        self,
        *,
        execution_id: int,
        rule_version: int,
        effective_config_snapshot: dict[str, Any],
    ) -> None:
        session_factory = session.async_session_factory
        if session_factory is None:
            raise ScrapingFailedException("Database is not initialized")
        async with session_factory() as db_session:
            execution_repo = TaskExecutionRepository(db_session)
            execution = await execution_repo.get_by_id(execution_id)
            if execution is None:
                return
            await execution_repo.update(
                execution,
                {
                    "status": TaskExecutionStatus.RUNNING,
                    "rule_version": rule_version,
                    "effective_config_snapshot": effective_config_snapshot,
                },
            )
            await db_session.commit()

    async def _mark_success(
        self,
        *,
        execution_id: int,
        rule_id: int,
        rule_execution_id: str,
        processed_rows: int,
        result: dict[str, Any],
    ) -> None:
        session_factory = session.async_session_factory
        if session_factory is None:
            raise ScrapingFailedException("Database is not initialized")
        async with session_factory() as db_session:
            execution_repo = TaskExecutionRepository(db_session)
            execution = await execution_repo.get_by_id(execution_id)
            if execution is None:
                return
            completed_at = execution.completed_at or datetime.now(tz=UTC)
            snapshot = dict(execution.effective_config_snapshot or {})
            snapshot["result"] = dict(result)
            await execution_repo.update(
                execution,
                {
                    "status": TaskExecutionStatus.SUCCESS,
                    "processed_rows": processed_rows,
                    "effective_config_snapshot": snapshot,
                    "error_message": "",
                },
            )
            rule_repo = ScrapingRuleRepository(db_session)
            rule = await rule_repo.get_by_id(rule_id)
            if rule is not None:
                normalized_execution_id = str(rule_execution_id or "").strip()
                rule.last_executed_at = completed_at
                rule.last_execution_id = (
                    normalized_execution_id[:100] if normalized_execution_id else None
                )
            await db_session.commit()

    async def _mark_failed(
        self,
        *,
        execution_id: int,
        error_message: str,
    ) -> None:
        session_factory = session.async_session_factory
        if session_factory is None:
            return
        async with session_factory() as db_session:
            execution_repo = TaskExecutionRepository(db_session)
            execution = await execution_repo.get_by_id(execution_id)
            if execution is None:
                return
            await execution_repo.update(
                execution,
                {
                    "status": TaskExecutionStatus.FAILED,
                    "error_message": error_message[:1000],
                },
            )
            await db_session.commit()

    async def _collect_and_persist(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        data_source_id: int,
        rule_id: int,
        execution_id: str,
        queue_task_id: str,
        redis_client: Any | None,
        session_factory,
    ) -> dict[str, Any]:
        plan_units = self.plan_builder.build(runtime)
        if not plan_units:
            raise ShopDashboardNoTargetShopsException(
                "No target shops resolved",
                error_data={
                    "data_source_id": data_source_id,
                    "rule_id": rule_id,
                    "execution_id": execution_id,
                    "reason": "empty_target_shops",
                },
            )

        from src.tasks.collection import douyin_shop_dashboard as task_module

        resolved_redis = self._resolve_redis_client(redis_client)
        rate_limiter_cls = getattr(task_module, "_RateLimiter")
        build_business_key = getattr(task_module, "_build_business_key")
        collect_one_day = getattr(task_module, "_collect_one_day")
        materialize_runtime_storage_state = getattr(
            task_module,
            "_materialize_runtime_storage_state",
        )
        helper_cls = getattr(
            task_module,
            "FunboostIdempotencyHelper",
            FunboostIdempotencyHelper,
        )
        helper = helper_cls(
            redis_client=resolved_redis,
            task_name="sync_shop_dashboard",
        )
        state_store_cls = getattr(task_module, "SessionStateStore", SessionStateStore)
        state_store = state_store_cls(
            base_dir=Path(".runtime") / "shop_dashboard_state"
        )
        runtime = materialize_runtime_storage_state(runtime, state_store)
        runtimes_by_shop: dict[str, ShopDashboardRuntimeConfig] = {
            runtime.shop_id: runtime,
        }
        for plan_unit in plan_units:
            if plan_unit.shop_id in runtimes_by_shop:
                continue
            runtimes_by_shop[plan_unit.shop_id] = replace(
                runtime, shop_id=plan_unit.shop_id
            )

        browser_cls = getattr(task_module, "BrowserScraper", BrowserScraper)
        lock_manager_cls = getattr(task_module, "LockManager", LockManager)
        login_state_manager_cls = getattr(
            task_module,
            "LoginStateManager",
            LoginStateManager,
        )
        bootstrapper_cls = getattr(
            task_module,
            "SessionBootstrapper",
            SessionBootstrapper,
        )
        browser = browser_cls()
        lock_manager = lock_manager_cls(redis_client=resolved_redis)
        login_state_manager = login_state_manager_cls(
            state_store=state_store,
            redis_client=resolved_redis,
        )
        bootstrapper = bootstrapper_cls(
            state_store=state_store,
            browser_scraper=browser,
        )
        collector_supports_shared_helpers = _supports_shared_helpers(collect_one_day)
        rate_limiter = rate_limiter_cls(runtime.rate_limit)
        items: list[dict[str, Any]] = []
        requested_shop_ids = list(runtime.resolved_shop_ids)
        if not requested_shop_ids:
            requested_shop_ids = list({plan_unit.shop_id for plan_unit in plan_units})
        verify_metric_date_by_shop: dict[str, str] = {}
        for plan_unit in plan_units:
            if plan_unit.shop_id in verify_metric_date_by_shop:
                continue
            verify_metric_date_by_shop[plan_unit.shop_id] = plan_unit.metric_date
        bootstrap_results = await self._bootstrap_shops(
            bootstrapper=bootstrapper,
            runtime=runtime,
            shop_ids=requested_shop_ids,
            verify_metric_date_by_shop=verify_metric_date_by_shop,
        )
        capability_service = ShopSwitchCapabilityService(redis_client=resolved_redis)
        bootstrap_rebuild_count = 0
        bootstrap_verify_failed_count = 0
        shop_mismatch_count = 0
        shop_circuit_break_count = 0
        account_switch_unsupported_count = 0

        for plan_unit in plan_units:
            rate_limiter.wait()
            unit_runtime = runtimes_by_shop[plan_unit.shop_id]
            storage_account_id = self._resolve_storage_account_id(
                runtime=unit_runtime,
                shop_id=plan_unit.shop_id,
            )
            capability_account_id = capability_service.resolve_capability_account_id(
                str(unit_runtime.account_id or "").strip()
            )
            account_id_status = (
                "stable" if capability_account_id else "account_id_unstable"
            )
            if (
                capability_account_id
                and capability_service.is_unsupported_http_shop_switch(
                    capability_account_id
                )
            ):
                account_switch_unsupported_count += 1
                observe_shop_dashboard_account_switch_unsupported()
                unsupported_item = {
                    "status": "failed",
                    "reason": "account_shop_switch_unsupported",
                    "metric_date": plan_unit.metric_date,
                    "shop_id": unit_runtime.shop_id,
                    "target_shop_id": plan_unit.shop_id,
                    "actual_shop_id": None,
                    "mismatch_status": "unsupported",
                    "rule_id": unit_runtime.rule_id,
                    "execution_id": unit_runtime.execution_id,
                    "retry_count": 0,
                    "fallback_trace": [],
                    "error_code": "account_shop_switch_unsupported",
                    "recommended_collection_mode": "per_shop_account",
                    "account_id": capability_account_id,
                    "account_id_status": account_id_status,
                }
                items.append(unsupported_item)
                observe_shop_dashboard_collection(
                    source="capability",
                    status="failed",
                    duration_seconds=0.0,
                    shop_mode=runtime.shop_mode,
                    shop_resolve_source=runtime.shop_resolve_source,
                    bootstrap_status="skipped",
                    circuit_break_status="closed",
                )
                continue
            if self._is_shop_circuit_open(
                redis_client=resolved_redis,
                account_id=storage_account_id,
                shop_id=plan_unit.shop_id,
            ):
                shop_circuit_break_count += 1
                circuit_item = {
                    "status": "failed",
                    "reason": "shop_circuit_break",
                    "metric_date": plan_unit.metric_date,
                    "shop_id": unit_runtime.shop_id,
                    "target_shop_id": plan_unit.shop_id,
                    "actual_shop_id": None,
                    "mismatch_status": "circuit_break",
                    "rule_id": unit_runtime.rule_id,
                    "execution_id": unit_runtime.execution_id,
                    "retry_count": 0,
                    "fallback_trace": [],
                    "account_id_status": account_id_status,
                }
                items.append(circuit_item)
                observe_shop_dashboard_collection(
                    source="circuit_break",
                    status="failed",
                    duration_seconds=0.0,
                    shop_mode=runtime.shop_mode,
                    shop_resolve_source=runtime.shop_resolve_source,
                    bootstrap_status="skipped",
                    circuit_break_status="open",
                )
                continue
            bundle = state_store.load_bundle(storage_account_id, plan_unit.shop_id)
            if not bundle:
                bootstrap_result = await self._bootstrap_shop(
                    bootstrapper=bootstrapper,
                    runtime=unit_runtime,
                    shop_id=plan_unit.shop_id,
                    verify_metric_date=plan_unit.metric_date,
                )
                bootstrap_results[plan_unit.shop_id] = bootstrap_result
                bootstrap_rebuild_count += 1
                bundle = state_store.load_bundle(storage_account_id, plan_unit.shop_id)
            if bundle:
                bundle_cookies = bundle.get("cookies")
                bundle_common_query = bundle.get("common_query")
                if isinstance(bundle_cookies, dict):
                    unit_runtime = replace(unit_runtime, cookies=dict(bundle_cookies))
                if isinstance(bundle_common_query, dict):
                    merged_common_query = dict(unit_runtime.common_query)
                    merged_common_query.update(bundle_common_query)
                    unit_runtime = replace(
                        unit_runtime,
                        common_query=merged_common_query,
                    )
            bootstrap_result = bootstrap_results.get(plan_unit.shop_id)
            if isinstance(bootstrap_result, dict) and bool(
                bootstrap_result.get("bootstrap_failed")
            ):
                bootstrap_error_code = str(
                    bootstrap_result.get("error_code") or "verify_request_failed"
                ).strip()
                bootstrap_error = str(bootstrap_result.get("error") or "").strip()
                bootstrap_verify_failed_count += 1
                observe_shop_dashboard_bootstrap_verify_failed(
                    error_code=bootstrap_error_code
                )
                mismatch_state: dict[str, Any] | None = None
                actual_shop_id = str(
                    bootstrap_result.get("actual_shop_id")
                    or bootstrap_result.get("bootstrap_verify_actual_shop_id")
                    or ""
                ).strip()
                if bootstrap_error_code == "verify_shop_mismatch":
                    shop_mismatch_count += 1
                    mismatch_state = self._record_shop_mismatch_failure(
                        redis_client=resolved_redis,
                        account_id=storage_account_id,
                        shop_id=plan_unit.shop_id,
                    )
                    if bool(mismatch_state.get("circuit_open")):
                        shop_circuit_break_count += 1
                    if capability_account_id and actual_shop_id:
                        capability_evidence = (
                            capability_service.record_mismatch_evidence(
                                account_id=capability_account_id,
                                target_shop_id=plan_unit.shop_id,
                                actual_shop_id=actual_shop_id,
                            )
                        )
                        if bool(capability_evidence.get("unsupported")):
                            account_switch_unsupported_count += 1
                            observe_shop_dashboard_account_switch_unsupported()
                failed_item = {
                    "status": "failed",
                    "reason": "bootstrap_verify_failed",
                    "metric_date": plan_unit.metric_date,
                    "shop_id": unit_runtime.shop_id,
                    "target_shop_id": plan_unit.shop_id,
                    "actual_shop_id": actual_shop_id or None,
                    "mismatch_status": (
                        "mismatched"
                        if bootstrap_error_code == "verify_shop_mismatch"
                        else "unknown"
                    ),
                    "rule_id": unit_runtime.rule_id,
                    "execution_id": unit_runtime.execution_id,
                    "retry_count": 0,
                    "fallback_trace": [],
                    "error_code": bootstrap_error_code,
                    "bootstrap_choose_status": str(
                        bootstrap_result.get("bootstrap_choose_status") or "unknown"
                    ),
                    "bootstrap_verify_status": str(
                        bootstrap_result.get("bootstrap_verify_status") or "failed"
                    ),
                    "bootstrap_verify_actual_shop_id": str(
                        bootstrap_result.get("bootstrap_verify_actual_shop_id") or ""
                    ),
                    "bootstrap_verify_error_code": str(
                        bootstrap_result.get("bootstrap_verify_error_code")
                        or bootstrap_error_code
                    ),
                    "account_id_status": account_id_status,
                }
                if mismatch_state is not None:
                    failed_item["error_data"] = {
                        "mismatch_fail_count": mismatch_state.get("count", 0),
                        "circuit_open": bool(mismatch_state.get("circuit_open", False)),
                    }
                if bootstrap_error:
                    failed_item["error"] = bootstrap_error
                items.append(failed_item)
                observe_shop_dashboard_collection(
                    source="bootstrap",
                    status="failed",
                    duration_seconds=0.0,
                    shop_mode=runtime.shop_mode,
                    shop_resolve_source=runtime.shop_resolve_source,
                    bootstrap_status="failed",
                    circuit_break_status=(
                        "open"
                        if bool(
                            mismatch_state and mismatch_state.get("circuit_open", False)
                        )
                        else "closed"
                    ),
                )
                continue
            business_key = build_business_key(
                unit_runtime,
                plan_unit.metric_date,
                plan_unit=plan_unit,
                queue_task_id=queue_task_id,
            )
            cached = helper.get_cached_result(business_key)
            if cached:
                if isinstance(cached, dict) and "account_id_status" not in cached:
                    cached["account_id_status"] = account_id_status
                items.append(cached)
                observe_shop_dashboard_collection(
                    source=str(cached.get("source", "cache")),
                    status=str(cached.get("status", "success")),
                    duration_seconds=0.0,
                    shop_mode=runtime.shop_mode,
                    shop_resolve_source=runtime.shop_resolve_source,
                    bootstrap_status="cached",
                    circuit_break_status="closed",
                )
                continue

            token = helper.acquire_lock(
                business_key,
                ttl=get_settings().shop_dashboard.lock_ttl_seconds,
            )
            if not token:
                skipped_result = {
                    "status": "skipped",
                    "reason": "running",
                    "metric_date": plan_unit.metric_date,
                    "shop_id": unit_runtime.shop_id,
                    "rule_id": unit_runtime.rule_id,
                    "execution_id": unit_runtime.execution_id,
                    "retry_count": 0,
                    "fallback_trace": [],
                    "account_id_status": account_id_status,
                }
                items.append(skipped_result)
                observe_shop_dashboard_collection(
                    source="lock",
                    status="skipped",
                    duration_seconds=0.0,
                    shop_mode=runtime.shop_mode,
                    shop_resolve_source=runtime.shop_resolve_source,
                    bootstrap_status="unknown",
                    circuit_break_status="closed",
                )
                continue

            started_at = time.perf_counter()
            source = "unknown"
            status = "failed"
            try:
                collected = self._collect_one_unit_payload(
                    collect_one_day=collect_one_day,
                    collector_supports_shared_helpers=collector_supports_shared_helpers,
                    runtime=unit_runtime,
                    metric_date=plan_unit.metric_date,
                    browser=browser,
                    lock_manager=lock_manager,
                    state_store=state_store,
                    login_state_manager=login_state_manager,
                )
                target_shop_id = plan_unit.shop_id
                actual_shop_id = self._resolve_actual_shop_id(
                    collected=collected,
                    fallback_shop_id=target_shop_id,
                )
                mismatch_status = (
                    "matched" if actual_shop_id == target_shop_id else "mismatched"
                )
                if mismatch_status == "mismatched":
                    shop_mismatch_count += 1
                    state_store.invalidate_bundle(storage_account_id, target_shop_id)
                    bootstrap_retry = await self._bootstrap_shop(
                        bootstrapper=bootstrapper,
                        runtime=unit_runtime,
                        shop_id=target_shop_id,
                        verify_metric_date=plan_unit.metric_date,
                    )
                    bootstrap_rebuild_count += 1
                    bootstrap_results[target_shop_id] = bootstrap_retry
                    if not bool(bootstrap_retry.get("bootstrap_failed")):
                        bundle = state_store.load_bundle(
                            storage_account_id,
                            target_shop_id,
                        )
                        if bundle:
                            bundle_cookies = bundle.get("cookies")
                            bundle_common_query = bundle.get("common_query")
                            if isinstance(bundle_cookies, dict):
                                unit_runtime = replace(
                                    unit_runtime,
                                    cookies=dict(bundle_cookies),
                                )
                            if isinstance(bundle_common_query, dict):
                                merged_common_query = dict(unit_runtime.common_query)
                                merged_common_query.update(bundle_common_query)
                                unit_runtime = replace(
                                    unit_runtime,
                                    common_query=merged_common_query,
                                )
                        collected = self._collect_one_unit_payload(
                            collect_one_day=collect_one_day,
                            collector_supports_shared_helpers=collector_supports_shared_helpers,
                            runtime=unit_runtime,
                            metric_date=plan_unit.metric_date,
                            browser=browser,
                            lock_manager=lock_manager,
                            state_store=state_store,
                            login_state_manager=login_state_manager,
                        )
                        actual_shop_id = self._resolve_actual_shop_id(
                            collected=collected,
                            fallback_shop_id=target_shop_id,
                        )
                        mismatch_status = (
                            "matched"
                            if actual_shop_id == target_shop_id
                            else "mismatched"
                        )
                collected["target_shop_id"] = target_shop_id
                collected["actual_shop_id"] = actual_shop_id
                collected["mismatch_status"] = mismatch_status
                collected["catalog_stale"] = bool(runtime.catalog_stale)
                collected["effective_filters_snapshot"] = dict(
                    plan_unit.effective_filters
                )
                collected["account_id_status"] = account_id_status
                if mismatch_status == "mismatched":
                    mismatch_state = self._record_shop_mismatch_failure(
                        redis_client=resolved_redis,
                        account_id=storage_account_id,
                        shop_id=target_shop_id,
                    )
                    if capability_account_id:
                        capability_evidence = (
                            capability_service.record_mismatch_evidence(
                                account_id=capability_account_id,
                                target_shop_id=target_shop_id,
                                actual_shop_id=actual_shop_id,
                            )
                        )
                        if bool(capability_evidence.get("unsupported")):
                            account_switch_unsupported_count += 1
                            observe_shop_dashboard_account_switch_unsupported()
                    if bool(mismatch_state.get("circuit_open")):
                        shop_circuit_break_count += 1
                    mismatch_result = {
                        "status": "failed",
                        "reason": "shop_mismatch",
                        "metric_date": plan_unit.metric_date,
                        "shop_id": target_shop_id,
                        "target_shop_id": target_shop_id,
                        "actual_shop_id": actual_shop_id,
                        "mismatch_status": "mismatched",
                        "catalog_stale": bool(runtime.catalog_stale),
                        "effective_filters_snapshot": dict(plan_unit.effective_filters),
                        "rule_id": unit_runtime.rule_id,
                        "execution_id": unit_runtime.execution_id,
                        "retry_count": int(collected.get("retry_count", 0)),
                        "fallback_trace": list(collected.get("fallback_trace", [])),
                        "account_id_status": account_id_status,
                        "error_data": {
                            "mismatch_fail_count": mismatch_state.get("count", 0),
                            "circuit_open": bool(
                                mismatch_state.get("circuit_open", False)
                            ),
                        },
                    }
                    items.append(mismatch_result)
                    source = str(collected.get("source", "unknown"))
                    status = "failed"
                    helper.cache_result(business_key, mismatch_result)
                    observe_shop_dashboard_collection(
                        source=source,
                        status=status,
                        duration_seconds=time.perf_counter() - started_at,
                        shop_mode=runtime.shop_mode,
                        shop_resolve_source=runtime.shop_resolve_source,
                        bootstrap_status="done",
                        circuit_break_status=(
                            "open"
                            if bool(mismatch_state.get("circuit_open", False))
                            else "closed"
                        ),
                    )
                    continue
                self._clear_shop_mismatch_failure(
                    redis_client=resolved_redis,
                    account_id=storage_account_id,
                    shop_id=target_shop_id,
                )
                if capability_account_id:
                    capability_service.clear_observation(capability_account_id)
                async with session_factory() as persist_session:
                    await self.result_persister.persist(
                        session=persist_session,
                        runtime=unit_runtime,
                        metric_date=plan_unit.metric_date,
                        payload=collected,
                    )
                helper.cache_result(business_key, collected)
                items.append(collected)
                source = str(collected.get("source", "unknown"))
                status = str(collected.get("status", "success"))
            except Exception:
                observe_shop_dashboard_collection(
                    source=source,
                    status=status,
                    duration_seconds=time.perf_counter() - started_at,
                    shop_mode=runtime.shop_mode,
                    shop_resolve_source=runtime.shop_resolve_source,
                    bootstrap_status="done",
                    circuit_break_status="closed",
                )
                raise
            else:
                observe_shop_dashboard_collection(
                    source=source,
                    status=status,
                    duration_seconds=time.perf_counter() - started_at,
                    shop_mode=runtime.shop_mode,
                    shop_resolve_source=runtime.shop_resolve_source,
                    bootstrap_status="done",
                    circuit_break_status="closed",
                )
            finally:
                helper.release_lock(business_key, token)

        return {
            "status": "success",
            "data_source_id": data_source_id,
            "rule_id": rule_id,
            "execution_id": execution_id,
            "requested_shop_count": len(requested_shop_ids),
            "resolved_shop_count": len({plan_unit.shop_id for plan_unit in plan_units}),
            "bootstrap_rebuild_count": bootstrap_rebuild_count,
            "bootstrap_verify_failed_count": bootstrap_verify_failed_count,
            "shop_mismatch_count": shop_mismatch_count,
            "shop_circuit_break_count": shop_circuit_break_count,
            "account_switch_unsupported_count": account_switch_unsupported_count,
            "catalog_stale": bool(runtime.catalog_stale),
            "shop_count": len({plan_unit.shop_id for plan_unit in plan_units}),
            "planned_units": len(plan_units),
            "completed_units": sum(
                1 for item in items if str(item.get("status", "success")) == "success"
            ),
            "failed_units": sum(
                1 for item in items if str(item.get("status", "success")) != "success"
            ),
            "items": items,
        }

    def _raise_when_all_units_failed(self, result: dict[str, Any]) -> None:
        planned_units = int(result.get("planned_units", 0) or 0)
        completed_units = int(result.get("completed_units", 0) or 0)
        failed_units = int(result.get("failed_units", 0) or 0)
        if planned_units <= 0:
            return
        if completed_units > 0:
            return
        if failed_units <= 0:
            return

        items = result.get("items")
        failed_items = [
            item
            for item in (items if isinstance(items, list) else [])
            if isinstance(item, dict)
            and str(item.get("status", "success")).lower() != "success"
        ]
        failure_reasons = [
            str(item.get("reason") or "").strip()
            for item in failed_items
            if str(item.get("reason") or "").strip()
        ]
        if (
            failed_items
            and len(failure_reasons) == len(failed_items)
            and all(
                reason == "account_shop_switch_unsupported"
                for reason in failure_reasons
            )
        ):
            result["recommended_collection_mode"] = "per_shop_account"
            return
        primary_error = ""
        for item in failed_items:
            reason = str(item.get("reason") or "").strip()
            error = str(item.get("error") or "").strip()
            if error:
                primary_error = f"{reason}: {error}" if reason else error
                break
            if reason:
                primary_error = reason
        message = "Collection failed: all planned units failed"
        if primary_error:
            message = f"{message}; {primary_error}"

        raise ScrapingFailedException(
            message,
            error_data={
                "planned_units": planned_units,
                "completed_units": completed_units,
                "failed_units": failed_units,
                "failure_reasons": failure_reasons,
                "primary_error": primary_error,
            },
        )

    def _collect_one_unit_payload(
        self,
        *,
        collect_one_day: Any,
        collector_supports_shared_helpers: bool,
        runtime: ShopDashboardRuntimeConfig,
        metric_date: str,
        browser: Any,
        lock_manager: Any,
        state_store: Any,
        login_state_manager: Any,
    ) -> dict[str, Any]:
        if collector_supports_shared_helpers:
            return collect_one_day(
                runtime,
                metric_date,
                browser,
                lock_manager=lock_manager,
                state_store=state_store,
                login_state_manager=login_state_manager,
            )
        return collect_one_day(
            runtime,
            metric_date,
            browser,
        )

    def _resolve_actual_shop_id(
        self,
        *,
        collected: dict[str, Any],
        fallback_shop_id: str,
    ) -> str:
        candidate = str(collected.get("actual_shop_id") or "").strip()
        if candidate:
            return candidate
        candidate = str(collected.get("shop_id") or "").strip()
        if candidate:
            return candidate
        return str(fallback_shop_id or "").strip()

    def _resolve_storage_account_id(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        shop_id: str,
    ) -> str:
        account_id = str(getattr(runtime, "account_id", "") or "").strip()
        if account_id:
            return account_id
        rule_id = int(getattr(runtime, "rule_id", 0) or 0)
        if rule_id > 0:
            return f"rule_{rule_id}"
        normalized_shop_id = str(shop_id or "").strip()
        if normalized_shop_id:
            return f"shop_{normalized_shop_id}"
        return "shop_anonymous"

    def _is_shop_circuit_open(
        self,
        *,
        redis_client: Any,
        account_id: str,
        shop_id: str,
    ) -> bool:
        circuit_key = redis_keys.shop_dashboard_shop_mismatch_circuit(
            account_id=account_id,
            shop_id=shop_id,
        )
        redis_get = getattr(redis_client, "get", None)
        if callable(redis_get):
            value = redis_get(circuit_key)
            return value not in {None, "", "0", 0, False}
        return False

    def _record_shop_mismatch_failure(
        self,
        *,
        redis_client: Any,
        account_id: str,
        shop_id: str,
    ) -> dict[str, Any]:
        settings = get_settings().shop_dashboard
        fail_count_key = redis_keys.shop_dashboard_shop_mismatch_fail_count(
            account_id=account_id,
            shop_id=shop_id,
        )
        circuit_key = redis_keys.shop_dashboard_shop_mismatch_circuit(
            account_id=account_id,
            shop_id=shop_id,
        )
        window_seconds = max(int(settings.shop_mismatch_failure_window_seconds), 1)
        threshold = max(self._resolve_shop_mismatch_threshold(account_id), 1)
        circuit_open_seconds = max(int(settings.shop_mismatch_circuit_open_seconds), 1)
        count = 0
        redis_incr = getattr(redis_client, "incr", None)
        redis_expire = getattr(redis_client, "expire", None)
        redis_get = getattr(redis_client, "get", None)
        redis_set = getattr(redis_client, "set", None)
        if callable(redis_incr):
            try:
                count = int(redis_incr(fail_count_key))
            except Exception:
                count = 0
        elif callable(redis_get) and callable(redis_set):
            current = redis_get(fail_count_key)
            try:
                count = int(current or 0) + 1
            except (TypeError, ValueError):
                count = 1
            redis_set(fail_count_key, count, ex=window_seconds)
        if count <= 0 and callable(redis_get):
            try:
                count = int(redis_get(fail_count_key) or 0)
            except (TypeError, ValueError):
                count = 0
        if callable(redis_expire):
            try:
                redis_expire(fail_count_key, window_seconds)
            except Exception:
                pass
        circuit_open = count >= threshold
        if circuit_open and callable(redis_set):
            redis_set(circuit_key, "1", ex=circuit_open_seconds)
        return {"count": count, "circuit_open": circuit_open}

    def _clear_shop_mismatch_failure(
        self,
        *,
        redis_client: Any,
        account_id: str,
        shop_id: str,
    ) -> None:
        fail_count_key = redis_keys.shop_dashboard_shop_mismatch_fail_count(
            account_id=account_id,
            shop_id=shop_id,
        )
        circuit_key = redis_keys.shop_dashboard_shop_mismatch_circuit(
            account_id=account_id,
            shop_id=shop_id,
        )
        redis_delete = getattr(redis_client, "delete", None)
        if callable(redis_delete):
            try:
                redis_delete(fail_count_key)
                redis_delete(circuit_key)
            except Exception:
                return
            return
        redis_set = getattr(redis_client, "set", None)
        if callable(redis_set):
            redis_set(fail_count_key, "0", ex=1)
            redis_set(circuit_key, "0", ex=1)

    def _resolve_shop_mismatch_threshold(self, account_id: str) -> int:
        settings = get_settings().shop_dashboard
        default_threshold = max(int(settings.shop_mismatch_failure_threshold), 1)
        degraded_threshold = int(settings.shop_mismatch_failure_threshold_degraded or 0)
        if degraded_threshold <= 0:
            return default_threshold
        configured_accounts = str(
            settings.shop_mismatch_failure_threshold_degraded_accounts or ""
        )
        candidates = {
            item.strip()
            for chunk in configured_accounts.split(",")
            for item in chunk.split("|")
            if item.strip()
        }
        if not candidates:
            return max(degraded_threshold, 1)
        if str(account_id or "").strip() in candidates:
            return max(degraded_threshold, 1)
        return default_threshold

    async def _bootstrap_shops(
        self,
        *,
        bootstrapper: Any,
        runtime: ShopDashboardRuntimeConfig,
        shop_ids: list[str],
        verify_metric_date_by_shop: Mapping[str, str],
    ) -> dict[str, dict[str, Any]]:
        bootstrap_shops = getattr(bootstrapper, "bootstrap_shops")
        kwargs: dict[str, Any] = {
            "runtime": runtime,
            "shop_ids": shop_ids,
        }
        if self._supports_keyword_argument(
            bootstrap_shops,
            "verify_metric_date_by_shop",
        ):
            kwargs["verify_metric_date_by_shop"] = dict(verify_metric_date_by_shop)
        result = bootstrap_shops(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, dict):
            return result
        return {}

    async def _bootstrap_shop(
        self,
        *,
        bootstrapper: Any,
        runtime: ShopDashboardRuntimeConfig,
        shop_id: str,
        verify_metric_date: str,
    ) -> dict[str, Any]:
        bootstrap_shop = getattr(bootstrapper, "bootstrap_shop")
        kwargs: dict[str, Any] = {
            "runtime": runtime,
            "shop_id": shop_id,
        }
        if self._supports_keyword_argument(bootstrap_shop, "verify_metric_date"):
            kwargs["verify_metric_date"] = verify_metric_date
        result = bootstrap_shop(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, dict):
            return result
        return {
            "shop_id": shop_id,
            "target_shop_id": shop_id,
            "bootstrap_failed": True,
            "status": "failed",
            "error": "bootstrap_result_invalid",
            "error_code": "verify_request_failed",
        }

    def _supports_keyword_argument(self, call: Any, argument_name: str) -> bool:
        try:
            signature = inspect.signature(call)
        except (TypeError, ValueError):
            return True
        for parameter in signature.parameters.values():
            if parameter.kind == inspect.Parameter.VAR_KEYWORD:
                return True
        return argument_name in signature.parameters

    def _build_idempotency_key(
        self,
        *,
        data_source_id: int,
        rule_id: int,
        execution_id: str,
        queue_task_id: str,
    ) -> str:
        scope = queue_task_id.strip() or execution_id
        return f"shop_dashboard:{data_source_id}:{rule_id}:{scope}"

    def _resolve_reused_result(self, execution: Any) -> dict[str, Any] | None:
        if execution.status != TaskExecutionStatus.SUCCESS:
            return None
        snapshot = execution.effective_config_snapshot
        if not isinstance(snapshot, dict):
            return None
        result = snapshot.get("result")
        if isinstance(result, dict):
            return dict(result)
        return None

    def _map_scraper_exception(self, exc: Exception) -> Exception:
        if isinstance(exc, ScrapingFailedException):
            return exc
        if isinstance(exc, ShopDashboardCookieExpiredException):
            return exc
        if isinstance(exc, ShopDashboardDataIncompleteException):
            return exc
        if isinstance(exc, ShopDashboardNoTargetShopsException):
            return exc
        if isinstance(exc, ShopDashboardShopMismatchException):
            return exc
        if isinstance(exc, ShopDashboardShopCircuitBreakException):
            return exc
        if isinstance(exc, LoginExpiredError):
            return ShopDashboardCookieExpiredException(
                str(exc),
                error_data=getattr(exc, "error_data", {}),
            )
        if isinstance(exc, DataIncompleteError):
            return ShopDashboardDataIncompleteException(
                str(exc),
                error_data=getattr(exc, "error_data", {}),
            )
        if isinstance(exc, ShopDashboardScraperError):
            return ScrapingFailedException(
                str(exc),
                error_data=getattr(exc, "error_data", {}),
            )
        return exc

    def _resolve_redis_client(self, redis_client: Any | None) -> Any:
        return resolve_sync_redis_client(redis_client)


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
