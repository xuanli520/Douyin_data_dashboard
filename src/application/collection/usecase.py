from __future__ import annotations

import inspect
import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from typing import Mapping

from redis import Redis
from sqlalchemy.exc import IntegrityError

from src import session
from src.application.collection.plan_builder import CollectionPlanBuilder
from src.application.collection.result_persister import CollectionResultPersister
from src.application.collection.runtime_loader import CollectionRuntimeLoader
from src.application.collection.runtime_loader import LoadedCollectionRuntime
from src.config import get_settings
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
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore
from src.tasks.exceptions import ScrapingFailedException
from src.tasks.exceptions import ShopDashboardCookieExpiredException
from src.tasks.exceptions import ShopDashboardDataIncompleteException
from src.tasks.idempotency import FunboostIdempotencyHelper


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
            raise ScrapingFailedException(
                "No target shops resolved",
                error_data={
                    "data_source_id": data_source_id,
                    "rule_id": rule_id,
                    "execution_id": execution_id,
                    "reason": "empty_target_shops",
                },
            )

        from src.tasks.collection import douyin_shop_dashboard as task_module
        from src.tasks.collection.douyin_shop_dashboard import (
            RateLimiter,
            build_business_key,
            collect_one_day,
            materialize_runtime_storage_state,
        )

        resolved_redis = self._resolve_redis_client(redis_client)
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
        browser = browser_cls()
        lock_manager = lock_manager_cls(redis_client=resolved_redis)
        login_state_manager = login_state_manager_cls(
            state_store=state_store,
            redis_client=resolved_redis,
        )
        collector_supports_shared_helpers = _supports_shared_helpers(collect_one_day)
        rate_limiter = RateLimiter(runtime.rate_limit)
        items: list[dict[str, Any]] = []

        for plan_unit in plan_units:
            rate_limiter.wait()
            unit_runtime = runtimes_by_shop[plan_unit.shop_id]
            business_key = build_business_key(
                unit_runtime,
                plan_unit.metric_date,
                plan_unit=plan_unit,
            )
            cache_enabled = _is_result_cache_enabled(runtime.execution_id)
            cached = helper.get_cached_result(business_key) if cache_enabled else None
            if cached:
                items.append(cached)
                observe_shop_dashboard_collection(
                    source=str(cached.get("source", "cache")),
                    status=str(cached.get("status", "success")),
                    duration_seconds=0.0,
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
                )
                continue

            started_at = time.perf_counter()
            source = "unknown"
            status = "failed"
            try:
                if collector_supports_shared_helpers:
                    collected = collect_one_day(
                        unit_runtime,
                        plan_unit.metric_date,
                        browser,
                        lock_manager=lock_manager,
                        state_store=state_store,
                        login_state_manager=login_state_manager,
                    )
                else:
                    collected = collect_one_day(
                        unit_runtime,
                        plan_unit.metric_date,
                        browser,
                    )
                async with session_factory() as persist_session:
                    await self.result_persister.persist(
                        session=persist_session,
                        runtime=unit_runtime,
                        metric_date=plan_unit.metric_date,
                        payload=collected,
                    )
                if cache_enabled:
                    helper.cache_result(business_key, collected)
                items.append(collected)
                source = str(collected.get("source", "unknown"))
                status = str(collected.get("status", "success"))
            except Exception:
                observe_shop_dashboard_collection(
                    source=source,
                    status=status,
                    duration_seconds=time.perf_counter() - started_at,
                )
                raise
            else:
                observe_shop_dashboard_collection(
                    source=source,
                    status=status,
                    duration_seconds=time.perf_counter() - started_at,
                )
            finally:
                helper.release_lock(business_key, token)

        return {
            "status": "success",
            "data_source_id": data_source_id,
            "rule_id": rule_id,
            "execution_id": execution_id,
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

    def _build_idempotency_key(
        self,
        *,
        data_source_id: int,
        rule_id: int,
        execution_id: str,
    ) -> str:
        return f"shop_dashboard:{data_source_id}:{rule_id}:{execution_id}"

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
        if redis_client is not None:
            return redis_client
        settings = get_settings()
        return Redis(
            host=settings.cache.host,
            port=settings.cache.port,
            db=settings.cache.db,
            password=settings.cache.password,
            encoding=settings.cache.encoding,
            decode_responses=True,
            socket_timeout=settings.cache.socket_timeout,
            socket_connect_timeout=settings.cache.socket_connect_timeout,
            retry_on_timeout=settings.cache.retry_on_timeout,
        )


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


def _is_result_cache_enabled(execution_id: str) -> bool:
    return not execution_id.startswith("cron_cookie_health_check_")
