from __future__ import annotations

import inspect
import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from typing import Mapping

from sqlalchemy.exc import IntegrityError

from src import session
from src.application.collection.plan_builder import CollectionPlanBuilder
from src.application.collection.result_persister import CollectionResultPersister
from src.application.collection.runtime_loader import CollectionRuntimeLoader
from src.application.collection.runtime_loader import LoadedCollectionRuntime
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
from src.domains.task.repository import TaskDefinitionRepository
from src.domains.task.repository import TaskExecutionRepository
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
                redis_client=redis_client,
                session_factory=session_factory,
            )
            await self._mark_success(
                execution_id=execution.id if execution.id is not None else 0,
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
        bootstrap_results = await bootstrapper.bootstrap_shops(
            runtime=runtime,
            shop_ids=requested_shop_ids,
        )
        bootstrap_rebuild_count = 0
        shop_mismatch_count = 0
        shop_circuit_break_count = 0

        for plan_unit in plan_units:
            rate_limiter.wait()
            unit_runtime = runtimes_by_shop[plan_unit.shop_id]
            account_id = str(unit_runtime.account_id or "").strip() or (
                f"shop_{plan_unit.shop_id}"
            )
            if self._is_shop_circuit_open(
                redis_client=resolved_redis,
                account_id=account_id,
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
            bundle = state_store.load_bundle(account_id, plan_unit.shop_id)
            if not bundle:
                bootstrap_result = await bootstrapper.bootstrap_shop(
                    runtime=unit_runtime,
                    shop_id=plan_unit.shop_id,
                )
                bootstrap_results[plan_unit.shop_id] = bootstrap_result
                bootstrap_rebuild_count += 1
                bundle = state_store.load_bundle(account_id, plan_unit.shop_id)
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
                failed_item = {
                    "status": "failed",
                    "reason": "bootstrap_failed",
                    "metric_date": plan_unit.metric_date,
                    "shop_id": unit_runtime.shop_id,
                    "rule_id": unit_runtime.rule_id,
                    "execution_id": unit_runtime.execution_id,
                    "retry_count": 0,
                    "fallback_trace": [],
                }
                items.append(failed_item)
                observe_shop_dashboard_collection(
                    source="bootstrap",
                    status="failed",
                    duration_seconds=0.0,
                    shop_mode=runtime.shop_mode,
                    shop_resolve_source=runtime.shop_resolve_source,
                    bootstrap_status="failed",
                    circuit_break_status="closed",
                )
                continue
            business_key = build_business_key(
                unit_runtime,
                plan_unit.metric_date,
                plan_unit=plan_unit,
            )
            cached = helper.get_cached_result(business_key)
            if cached:
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
                    state_store.invalidate_bundle(account_id, target_shop_id)
                    bootstrap_retry = await bootstrapper.bootstrap_shop(
                        runtime=unit_runtime,
                        shop_id=target_shop_id,
                    )
                    bootstrap_rebuild_count += 1
                    bootstrap_results[target_shop_id] = bootstrap_retry
                    if not bool(bootstrap_retry.get("bootstrap_failed")):
                        bundle = state_store.load_bundle(account_id, target_shop_id)
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
                if mismatch_status == "mismatched":
                    mismatch_state = self._record_shop_mismatch_failure(
                        redis_client=resolved_redis,
                        account_id=account_id,
                        shop_id=target_shop_id,
                    )
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
                    account_id=account_id,
                    shop_id=target_shop_id,
                )
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
            "shop_mismatch_count": shop_mismatch_count,
            "shop_circuit_break_count": shop_circuit_break_count,
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
        threshold = max(int(settings.shop_mismatch_failure_threshold), 1)
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
