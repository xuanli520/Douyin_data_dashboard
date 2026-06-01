from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from typing import Mapping

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from src import session
from src.application.collection.contracts import SessionFactory
from src.application.collection.executor import CollectionExecutor
from src.application.collection.executor import TaskModuleCollectionExecutor
from src.application.collection.browser_agent_adapter import (
    _recipe_payload_from_model,
)
from src.application.collection.browser_agent_adapter import load_agent_recipe_from_db
from src.application.collection.plan_builder_impl import CollectionPlanUnit
from src.application.collection.plan_builder_impl import build_collection_plan
from src.application.collection.redis_client import RedisClient
from src.application.collection.redis_client import resolve_collection_redis_client
from src.application.collection.result_persister import CollectionResultPersister
from src.application.collection.runtime_loader import CollectionRuntimeLoader
from src.application.collection.runtime_loader import LoadedCollectionRuntime
from src.config import get_settings
from src.core.agent import Recipe
from src.core.agent.exceptions import RecipeValidationError
from src.domains.agent_recipe.validation import is_shop_score_recipe
from src.domains.agent_recipe.validation import validate_stable_recipe
from src.domains.task.exceptions import ScrapingFailedException
from src.domains.task.exceptions import ShopDashboardNoTargetShopsException
from src.domains.task.exceptions import ShopDashboardCookieExpiredException
from src.domains.task.exceptions import ShopDashboardDataIncompleteException
from src.domains.task.exceptions import ShopDashboardShopCircuitBreakException
from src.domains.task.exceptions import ShopDashboardShopMismatchException
from src.domains.task.enums import TaskExecutionStatus
from src.domains.task.enums import TaskTriggerMode
from src.domains.task.enums import TaskType
from src.domains.agent_recipe.repository import AgentRecipeRepository
from src.domains.scraping_rule.repository import ScrapingRuleRepository
from src.domains.task.repository import TaskDefinitionRepository
from src.domains.task.repository import TaskExecutionRepository
from src.middleware.monitor import observe_shop_dashboard_collection
from src.scrapers.shop_dashboard.exceptions import DataIncompleteError
from src.scrapers.shop_dashboard.exceptions import LoginExpiredError
from src.scrapers.shop_dashboard.exceptions import ShopDashboardScraperError
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.shared.redis_keys import redis_keys


logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(slots=True)
class _BatchAgentContext:
    enabled: bool = False
    recipe_id: int | None = None
    recipe_version: int | None = None
    recipe_stability: str | None = None
    degraded: bool = False
    degraded_reason: str = ""
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _ensure_db_initialized() -> None:
    if session.async_session_factory is not None:
        return
    settings = get_settings()
    session.run_coro(session.init_db(settings.db.url, settings.db.echo))


async def _ensure_db_initialized_async() -> None:
    if session.async_session_factory is not None:
        return
    settings = get_settings()
    await session.init_db(settings.db.url, settings.db.echo)


def _resolve_state_store_base_dir() -> Path:
    configured = str(get_settings().shop_dashboard.runtime_state_dir or "").strip()
    if not configured:
        return _REPO_ROOT / ".runtime" / "shop_dashboard_state"
    state_dir = Path(configured).expanduser()
    if state_dir.is_absolute():
        return state_dir
    return _REPO_ROOT / state_dir


def _runtime_recipe_payload_from_model(value: Any) -> dict[str, Any]:
    payload = _recipe_payload_from_model(value)
    payload.pop("id", None)
    payload.pop("stability", None)
    return payload


class CollectionUseCase:
    _SHOP_MISMATCH_RECORD_SCRIPT = """
    local count = redis.call('incr', KEYS[1])
    redis.call('expire', KEYS[1], tonumber(ARGV[1]))
    local circuit_open = 0
    if count >= tonumber(ARGV[2]) then
        redis.call('set', KEYS[2], '1', 'EX', tonumber(ARGV[3]))
        circuit_open = 1
    end
    return {count, circuit_open}
    """

    def __init__(
        self,
        *,
        runtime_loader: CollectionRuntimeLoader | None = None,
        plan_builder: Callable[[ShopDashboardRuntimeConfig], list[CollectionPlanUnit]]
        | None = None,
        result_persister: CollectionResultPersister | None = None,
        executor: CollectionExecutor | None = None,
    ) -> None:
        self.runtime_loader = runtime_loader or CollectionRuntimeLoader()
        self.plan_builder = plan_builder or build_collection_plan
        self.result_persister = result_persister or CollectionResultPersister()
        self.executor = executor or TaskModuleCollectionExecutor()
        self._local_shop_mismatch_failures: dict[str, tuple[int, float]] = {}
        self._local_shop_mismatch_circuits: dict[str, float] = {}
        self._local_mismatch_warning_logged = False

    def execute(
        self,
        *,
        data_source_id: int,
        rule_id: int,
        execution_id: str,
        queue_task_id: str,
        started_at: datetime | None = None,
        triggered_by: int | None = None,
        overrides: Mapping[str, Any] | None = None,
        redis_client: Any | None = None,
    ) -> dict[str, Any]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "CollectionUseCase.execute cannot be called from an async context"
            )
        _ensure_db_initialized()
        return session.run_coro(
            self._execute_async(
                data_source_id=data_source_id,
                rule_id=rule_id,
                execution_id=execution_id,
                queue_task_id=queue_task_id,
                started_at=started_at,
                triggered_by=triggered_by,
                overrides=dict(overrides or {}),
                redis_client=redis_client,
            )
        )

    async def execute_async(
        self,
        *,
        data_source_id: int,
        rule_id: int,
        execution_id: str,
        queue_task_id: str,
        started_at: datetime | None = None,
        triggered_by: int | None = None,
        overrides: Mapping[str, Any] | None = None,
        redis_client: Any | None = None,
    ) -> dict[str, Any]:
        await _ensure_db_initialized_async()
        return await self._execute_async(
            data_source_id=data_source_id,
            rule_id=rule_id,
            execution_id=execution_id,
            queue_task_id=queue_task_id,
            started_at=started_at,
            triggered_by=triggered_by,
            overrides=dict(overrides or {}),
            redis_client=redis_client,
        )

    async def _execute_async(
        self,
        *,
        data_source_id: int,
        rule_id: int,
        execution_id: str,
        queue_task_id: str,
        started_at: datetime | None = None,
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
            started_at=started_at,
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
            resolved_redis_client = self._resolve_redis_client(redis_client)
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
                redis_client=resolved_redis_client,
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
            try:
                await self._mark_failed(
                    execution_id=execution.id if execution.id is not None else 0,
                    rule_id=rule_id,
                    rule_execution_id=execution_id,
                    error_message=str(mapped),
                )
            except Exception:
                logger.exception(
                    "failed to persist collection failure execution_id=%s rule_id=%s",
                    execution.id if execution.id is not None else 0,
                    rule_id,
                )
            if mapped is exc:
                raise
            raise mapped from exc

    async def _create_or_get_execution(
        self,
        *,
        data_source_id: int,
        rule_id: int,
        execution_id: str,
        queue_task_id: str,
        started_at: datetime | None,
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
                update_data = {
                    "idempotency_key": idempotency_key,
                    "payload": {
                        "data_source_id": data_source_id,
                        "rule_id": rule_id,
                        "execution_id": execution_id,
                        "overrides": dict(overrides),
                    },
                    "queue_task_id": queue_task_id,
                }
                if started_at is not None and existing_by_queue.started_at is None:
                    update_data["started_at"] = started_at
                if (
                    started_at is not None
                    and existing_by_queue.status == TaskExecutionStatus.QUEUED
                ):
                    update_data["status"] = TaskExecutionStatus.RUNNING
                execution = await execution_repo.update(
                    existing_by_queue,
                    update_data,
                )
                await db_session.commit()
                return execution

            task_repo = TaskDefinitionRepository(db_session)
            task = await task_repo.get_by_task_type(TaskType.SHOP_DASHBOARD_COLLECTION)
            if task is None:
                try:
                    task = await task_repo.create(
                        {
                            "name": "shop_dashboard_collection",
                            "task_type": TaskType.SHOP_DASHBOARD_COLLECTION,
                        }
                    )
                    await db_session.commit()
                except IntegrityError:
                    await db_session.rollback()
                    task = await task_repo.get_by_task_type(
                        TaskType.SHOP_DASHBOARD_COLLECTION
                    )
                    if task is None:
                        raise

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
                "status": (
                    TaskExecutionStatus.RUNNING
                    if started_at is not None
                    else TaskExecutionStatus.QUEUED
                ),
                "trigger_mode": trigger_mode,
                "payload": payload,
                "triggered_by": triggered_by,
                "idempotency_key": idempotency_key,
                "started_at": started_at,
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
                        update_data = {
                            "queue_task_id": queue_task_id,
                            "payload": payload,
                        }
                        if started_at is not None and existing.started_at is None:
                            update_data["started_at"] = started_at
                        if (
                            started_at is not None
                            and existing.status == TaskExecutionStatus.QUEUED
                        ):
                            update_data["status"] = TaskExecutionStatus.RUNNING
                        existing = await execution_repo.update(
                            existing,
                            update_data,
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
                    "completed_at": completed_at,
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
        rule_id: int,
        rule_execution_id: str,
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
            completed_at = execution.completed_at or datetime.now(tz=UTC)
            await execution_repo.update(
                execution,
                {
                    "status": TaskExecutionStatus.FAILED,
                    "completed_at": completed_at,
                    "error_message": error_message[:1000],
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

    async def _collect_and_persist(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        data_source_id: int,
        rule_id: int,
        execution_id: str,
        queue_task_id: str,
        redis_client: RedisClient,
        session_factory: SessionFactory,
    ) -> dict[str, Any]:
        plan_units = self.plan_builder(runtime)
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
        shop_count = len({unit.shop_id for unit in plan_units})
        runtime, batch_agent_context = await self._prepare_agent_recipe_context(
            runtime=runtime,
            plan_units=plan_units,
            shop_count=shop_count,
            session_factory=session_factory,
        )

        helper = self.executor.create_idempotency_helper(
            redis_client=redis_client,
            task_name="sync_shop_dashboard",
        )
        state_store = self.executor.create_state_store(
            base_dir=_resolve_state_store_base_dir()
        )
        runtime = self.executor.materialize_runtime_storage_state(
            runtime=runtime,
            state_store=state_store,
        )
        runtimes_by_shop: dict[str, ShopDashboardRuntimeConfig] = {
            runtime.shop_id: runtime,
        }
        for plan_unit in plan_units:
            if plan_unit.shop_id in runtimes_by_shop:
                continue
            runtimes_by_shop[plan_unit.shop_id] = replace(
                runtime, shop_id=plan_unit.shop_id
            )

        lock_manager = self.executor.create_lock_manager(redis_client=redis_client)
        login_state_manager = self.executor.create_login_state_manager(
            state_store=state_store,
            redis_client=redis_client,
        )
        rate_limiter = self.executor.create_rate_limiter(runtime.rate_limit)
        items: list[dict[str, Any]] = []
        requested_shop_ids = list(runtime.resolved_shop_ids)
        if not requested_shop_ids:
            requested_shop_ids = list({plan_unit.shop_id for plan_unit in plan_units})
        shop_mismatch_count = 0
        shop_circuit_break_count = 0

        if self._should_run_parallel_agent_batch(runtime, batch_agent_context):
            parallel_result = await self._collect_agent_batch_parallel(
                plan_units=plan_units,
                runtime=runtime,
                runtimes_by_shop=runtimes_by_shop,
                helper=helper,
                state_store=state_store,
                lock_manager=lock_manager,
                login_state_manager=login_state_manager,
                rate_limiter=rate_limiter,
                redis_client=redis_client,
                session_factory=session_factory,
                queue_task_id=queue_task_id,
                batch_agent_context=batch_agent_context,
            )
            items = list(parallel_result["items"])
            return {
                "status": "success",
                "data_source_id": data_source_id,
                "rule_id": rule_id,
                "execution_id": execution_id,
                "requested_shop_count": len(requested_shop_ids),
                "resolved_shop_count": shop_count,
                "shop_mismatch_count": int(
                    parallel_result.get("shop_mismatch_count", 0)
                ),
                "shop_circuit_break_count": int(
                    parallel_result.get("shop_circuit_break_count", 0)
                ),
                "catalog_stale": bool(runtime.catalog_stale),
                "shop_count": shop_count,
                "planned_units": len(plan_units),
                "completed_units": sum(
                    1
                    for item in items
                    if str(item.get("status", "success")) == "success"
                ),
                "failed_units": sum(
                    1
                    for item in items
                    if str(item.get("status", "success")) != "success"
                ),
                "items": items,
            }

        for plan_unit in plan_units:
            if batch_agent_context.degraded:
                items.append(
                    self._build_agent_recipe_failed_item(
                        runtime=runtimes_by_shop[plan_unit.shop_id],
                        plan_unit=plan_unit,
                        error_code="agent_recipe_degraded",
                        error=batch_agent_context.degraded_reason,
                        recipe_status="degraded",
                        recipe_stability=batch_agent_context.recipe_stability,
                    )
                )
                continue
            rate_limiter.wait()
            unit_runtime = runtimes_by_shop[plan_unit.shop_id]
            storage_account_id = self._resolve_storage_account_id(
                runtime=unit_runtime,
                shop_id=plan_unit.shop_id,
            )
            account_id_status = (
                "stable"
                if str(unit_runtime.account_id or "").strip()
                else "account_id_unstable"
            )
            if self._is_shop_circuit_open(
                redis_client=redis_client,
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
                    "agent_trace": [],
                    "account_id_status": account_id_status,
                }
                items.append(circuit_item)
                observe_shop_dashboard_collection(
                    source="circuit_break",
                    status="failed",
                    duration_seconds=0.0,
                    shop_mode=runtime.shop_mode,
                    shop_resolve_source=runtime.shop_resolve_source,
                    circuit_break_status="open",
                )
                continue
            business_key = self.executor.build_business_key(
                unit_runtime,
                plan_unit.metric_date,
                plan_unit=plan_unit,
                queue_task_id=queue_task_id,
            )
            cached = helper.get_cached_result(business_key)
            if cached:
                if isinstance(cached, dict) and "account_id_status" not in cached:
                    cached["account_id_status"] = account_id_status
                await self._persist_payload(
                    session_factory=session_factory,
                    runtime=unit_runtime,
                    metric_date=plan_unit.metric_date,
                    payload=cached,
                )
                items.append(cached)
                observe_shop_dashboard_collection(
                    source=str(cached.get("source", "cache")),
                    status=str(cached.get("status", "success")),
                    duration_seconds=0.0,
                    shop_mode=runtime.shop_mode,
                    shop_resolve_source=runtime.shop_resolve_source,
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
                    "target_shop_id": unit_runtime.shop_id,
                    "actual_shop_id": None,
                    "mismatch_status": "unknown",
                    "rule_id": unit_runtime.rule_id,
                    "execution_id": unit_runtime.execution_id,
                    "retry_count": 0,
                    "agent_trace": [],
                    "account_id_status": account_id_status,
                }
                items.append(skipped_result)
                observe_shop_dashboard_collection(
                    source="lock",
                    status="skipped",
                    duration_seconds=0.0,
                    shop_mode=runtime.shop_mode,
                    shop_resolve_source=runtime.shop_resolve_source,
                    circuit_break_status="closed",
                )
                continue

            started_at = time.perf_counter()
            source = "unknown"
            status = "failed"
            try:
                collected = await self._collect_unit_payload(
                    runtime=unit_runtime,
                    metric_date=plan_unit.metric_date,
                    plan_unit=plan_unit,
                    lock_manager=lock_manager,
                    state_store=state_store,
                    login_state_manager=login_state_manager,
                    session_factory=session_factory,
                )
                target_shop_id = plan_unit.shop_id
                actual_shop_id = self._resolve_actual_shop_id(
                    collected=collected,
                    fallback_shop_id=target_shop_id,
                )
                mismatch_status = (
                    "matched" if actual_shop_id == target_shop_id else "mismatched"
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
                        redis_client=redis_client,
                        account_id=storage_account_id,
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
                        "agent_trace": list(collected.get("agent_trace", [])),
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
                        circuit_break_status=(
                            "open"
                            if bool(mismatch_state.get("circuit_open", False))
                            else "closed"
                        ),
                    )
                    continue
                self._clear_shop_mismatch_failure(
                    redis_client=redis_client,
                    account_id=storage_account_id,
                    shop_id=target_shop_id,
                )
                await self._persist_payload(
                    session_factory=session_factory,
                    runtime=unit_runtime,
                    metric_date=plan_unit.metric_date,
                    payload=collected,
                )
                if self._is_success_payload(collected):
                    helper.cache_result(business_key, collected)
                items.append(collected)
                source = str(collected.get("source", "unknown"))
                status = str(collected.get("status", "success"))
            except Exception as exc:
                if batch_agent_context.enabled and self._is_agent_recipe_failure(exc):
                    error_code = self._extract_agent_failure_code(exc)
                    await self._mark_batch_recipe_degraded(
                        context=batch_agent_context,
                        reason=error_code,
                        session_factory=session_factory,
                    )
                    failed_item = self._build_agent_recipe_failed_item(
                        runtime=unit_runtime,
                        plan_unit=plan_unit,
                        error_code=error_code,
                        error=str(exc),
                        recipe_status="degraded",
                        recipe_stability=batch_agent_context.recipe_stability,
                    )
                    items.append(failed_item)
                    source = "browser_agent"
                    status = "failed"
                    observe_shop_dashboard_collection(
                        source=source,
                        status=status,
                        duration_seconds=time.perf_counter() - started_at,
                        shop_mode=runtime.shop_mode,
                        shop_resolve_source=runtime.shop_resolve_source,
                        circuit_break_status="closed",
                    )
                    continue
                if shop_count > 1 and self._is_recoverable_unit_failure(exc):
                    error_code = self._extract_agent_failure_code(exc)
                    failed_item = self._build_recoverable_unit_failed_item(
                        runtime=unit_runtime,
                        plan_unit=plan_unit,
                        error_code=error_code,
                        error=str(exc),
                        account_id_status=account_id_status,
                    )
                    await self._persist_payload(
                        session_factory=session_factory,
                        runtime=unit_runtime,
                        metric_date=plan_unit.metric_date,
                        payload=failed_item,
                    )
                    items.append(failed_item)
                    source = "browser_agent"
                    status = "failed"
                    observe_shop_dashboard_collection(
                        source=source,
                        status=status,
                        duration_seconds=time.perf_counter() - started_at,
                        shop_mode=runtime.shop_mode,
                        shop_resolve_source=runtime.shop_resolve_source,
                        circuit_break_status="closed",
                    )
                    continue
                observe_shop_dashboard_collection(
                    source=source,
                    status=status,
                    duration_seconds=time.perf_counter() - started_at,
                    shop_mode=runtime.shop_mode,
                    shop_resolve_source=runtime.shop_resolve_source,
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
            "resolved_shop_count": shop_count,
            "shop_mismatch_count": shop_mismatch_count,
            "shop_circuit_break_count": shop_circuit_break_count,
            "catalog_stale": bool(runtime.catalog_stale),
            "shop_count": shop_count,
            "planned_units": len(plan_units),
            "completed_units": sum(
                1 for item in items if str(item.get("status", "success")) == "success"
            ),
            "failed_units": sum(
                1 for item in items if str(item.get("status", "success")) != "success"
            ),
            "items": items,
        }

    def _should_run_parallel_agent_batch(
        self,
        runtime: ShopDashboardRuntimeConfig,
        context: _BatchAgentContext,
    ) -> bool:
        if not context.enabled:
            return False
        limit = int(get_settings().shop_dashboard.agent_batch_concurrency_limit or 1)
        return limit > 1

    async def _collect_agent_batch_parallel(
        self,
        *,
        plan_units: list[CollectionPlanUnit],
        runtime: ShopDashboardRuntimeConfig,
        runtimes_by_shop: dict[str, ShopDashboardRuntimeConfig],
        helper: Any,
        state_store: Any,
        lock_manager: Any,
        login_state_manager: Any,
        rate_limiter: Any,
        redis_client: RedisClient,
        session_factory: SessionFactory,
        queue_task_id: str,
        batch_agent_context: _BatchAgentContext,
    ) -> dict[str, Any]:
        limit = max(
            int(get_settings().shop_dashboard.agent_batch_concurrency_limit or 1),
            1,
        )
        queue: asyncio.Queue[CollectionPlanUnit] = asyncio.Queue()
        for plan_unit in plan_units:
            queue.put_nowait(plan_unit)
        results: list[tuple[int, dict[str, Any]]] = []
        counts = {
            "shop_mismatch_count": 0,
            "shop_circuit_break_count": 0,
        }
        errors: list[Exception] = []

        async def worker() -> None:
            while not errors:
                try:
                    plan_unit = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    outcome = await self._collect_agent_batch_unit(
                        runtime=runtime,
                        unit_runtime=runtimes_by_shop[plan_unit.shop_id],
                        plan_unit=plan_unit,
                        helper=helper,
                        state_store=state_store,
                        lock_manager=lock_manager,
                        login_state_manager=login_state_manager,
                        rate_limiter=rate_limiter,
                        redis_client=redis_client,
                        session_factory=session_factory,
                        queue_task_id=queue_task_id,
                        batch_agent_context=batch_agent_context,
                    )
                    for item in outcome["items"]:
                        results.append((plan_unit.plan_index, item))
                    for key in counts:
                        counts[key] += int(outcome.get(key, 0) or 0)
                except Exception as exc:
                    errors.append(exc)
                finally:
                    queue.task_done()

        worker_count = min(limit, len(plan_units))
        workers = [asyncio.create_task(worker()) for _ in range(worker_count)]
        await asyncio.gather(*workers)
        if errors:
            raise errors[0]
        ordered_items = [item for _, item in sorted(results, key=lambda pair: pair[0])]
        return {"items": ordered_items, **counts}

    async def _collect_agent_batch_unit(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        unit_runtime: ShopDashboardRuntimeConfig,
        plan_unit: CollectionPlanUnit,
        helper: Any,
        state_store: Any,
        lock_manager: Any,
        login_state_manager: Any,
        rate_limiter: Any,
        redis_client: RedisClient,
        session_factory: SessionFactory,
        queue_task_id: str,
        batch_agent_context: _BatchAgentContext,
    ) -> dict[str, Any]:
        if batch_agent_context.degraded:
            return {
                "items": [
                    self._build_agent_recipe_failed_item(
                        runtime=unit_runtime,
                        plan_unit=plan_unit,
                        error_code="agent_recipe_degraded",
                        error=batch_agent_context.degraded_reason,
                        recipe_status="degraded",
                        recipe_stability=batch_agent_context.recipe_stability,
                    )
                ]
            }
        await asyncio.to_thread(rate_limiter.wait)
        storage_account_id = self._resolve_storage_account_id(
            runtime=unit_runtime,
            shop_id=plan_unit.shop_id,
        )
        account_id_status = (
            "stable"
            if str(unit_runtime.account_id or "").strip()
            else "account_id_unstable"
        )
        if self._is_shop_circuit_open(
            redis_client=redis_client,
            account_id=storage_account_id,
            shop_id=plan_unit.shop_id,
        ):
            item = {
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
                "agent_trace": [],
                "account_id_status": account_id_status,
            }
            observe_shop_dashboard_collection(
                source="circuit_break",
                status="failed",
                duration_seconds=0.0,
                shop_mode=runtime.shop_mode,
                shop_resolve_source=runtime.shop_resolve_source,
                circuit_break_status="open",
            )
            return {"items": [item], "shop_circuit_break_count": 1}

        business_key = self.executor.build_business_key(
            unit_runtime,
            plan_unit.metric_date,
            plan_unit=plan_unit,
            queue_task_id=queue_task_id,
        )
        cached = helper.get_cached_result(business_key)
        if cached:
            if isinstance(cached, dict) and "account_id_status" not in cached:
                cached["account_id_status"] = account_id_status
            await self._persist_payload(
                session_factory=session_factory,
                runtime=unit_runtime,
                metric_date=plan_unit.metric_date,
                payload=cached,
            )
            observe_shop_dashboard_collection(
                source=str(cached.get("source", "cache")),
                status=str(cached.get("status", "success")),
                duration_seconds=0.0,
                shop_mode=runtime.shop_mode,
                shop_resolve_source=runtime.shop_resolve_source,
                circuit_break_status="closed",
            )
            return {"items": [cached]}

        token = helper.acquire_lock(
            business_key,
            ttl=get_settings().shop_dashboard.lock_ttl_seconds,
        )
        if not token:
            item = {
                "status": "skipped",
                "reason": "running",
                "metric_date": plan_unit.metric_date,
                "shop_id": unit_runtime.shop_id,
                "target_shop_id": unit_runtime.shop_id,
                "actual_shop_id": None,
                "mismatch_status": "unknown",
                "rule_id": unit_runtime.rule_id,
                "execution_id": unit_runtime.execution_id,
                "retry_count": 0,
                "agent_trace": [],
                "account_id_status": account_id_status,
            }
            observe_shop_dashboard_collection(
                source="lock",
                status="skipped",
                duration_seconds=0.0,
                shop_mode=runtime.shop_mode,
                shop_resolve_source=runtime.shop_resolve_source,
                circuit_break_status="closed",
            )
            return {"items": [item]}

        started_at = time.perf_counter()
        source = "unknown"
        status = "failed"
        try:
            collected = await self._collect_unit_payload(
                runtime=unit_runtime,
                metric_date=plan_unit.metric_date,
                plan_unit=plan_unit,
                lock_manager=lock_manager,
                state_store=state_store,
                login_state_manager=login_state_manager,
                session_factory=session_factory,
            )
            target_shop_id = plan_unit.shop_id
            actual_shop_id = self._resolve_actual_shop_id(
                collected=collected,
                fallback_shop_id=target_shop_id,
            )
            mismatch_status = (
                "matched" if actual_shop_id == target_shop_id else "mismatched"
            )
            collected["target_shop_id"] = target_shop_id
            collected["actual_shop_id"] = actual_shop_id
            collected["mismatch_status"] = mismatch_status
            collected["catalog_stale"] = bool(runtime.catalog_stale)
            collected["effective_filters_snapshot"] = dict(plan_unit.effective_filters)
            collected["account_id_status"] = account_id_status
            source = str(collected.get("source", "unknown"))
            status = str(collected.get("status", "success"))
            if mismatch_status == "mismatched":
                mismatch_state = self._record_shop_mismatch_failure(
                    redis_client=redis_client,
                    account_id=storage_account_id,
                    shop_id=target_shop_id,
                )
                item = {
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
                    "agent_trace": list(collected.get("agent_trace", [])),
                    "account_id_status": account_id_status,
                    "error_data": {
                        "mismatch_fail_count": mismatch_state.get("count", 0),
                        "circuit_open": bool(mismatch_state.get("circuit_open", False)),
                    },
                }
                helper.cache_result(business_key, item)
                observe_shop_dashboard_collection(
                    source=source,
                    status="failed",
                    duration_seconds=time.perf_counter() - started_at,
                    shop_mode=runtime.shop_mode,
                    shop_resolve_source=runtime.shop_resolve_source,
                    circuit_break_status=(
                        "open"
                        if bool(mismatch_state.get("circuit_open", False))
                        else "closed"
                    ),
                )
                return {
                    "items": [item],
                    "shop_mismatch_count": 1,
                    "shop_circuit_break_count": int(
                        bool(mismatch_state.get("circuit_open", False))
                    ),
                }
            self._clear_shop_mismatch_failure(
                redis_client=redis_client,
                account_id=storage_account_id,
                shop_id=target_shop_id,
            )
            await self._persist_payload(
                session_factory=session_factory,
                runtime=unit_runtime,
                metric_date=plan_unit.metric_date,
                payload=collected,
            )
            if self._is_success_payload(collected):
                helper.cache_result(business_key, collected)
            observe_shop_dashboard_collection(
                source=source,
                status=status,
                duration_seconds=time.perf_counter() - started_at,
                shop_mode=runtime.shop_mode,
                shop_resolve_source=runtime.shop_resolve_source,
                circuit_break_status="closed",
            )
            return {"items": [collected]}
        except Exception as exc:
            if batch_agent_context.enabled and self._is_agent_recipe_failure(exc):
                error_code = self._extract_agent_failure_code(exc)
                await self._mark_batch_recipe_degraded(
                    context=batch_agent_context,
                    reason=error_code,
                    session_factory=session_factory,
                )
                item = self._build_agent_recipe_failed_item(
                    runtime=unit_runtime,
                    plan_unit=plan_unit,
                    error_code=error_code,
                    error=str(exc),
                    recipe_status="degraded",
                    recipe_stability=batch_agent_context.recipe_stability,
                )
                observe_shop_dashboard_collection(
                    source="browser_agent",
                    status="failed",
                    duration_seconds=time.perf_counter() - started_at,
                    shop_mode=runtime.shop_mode,
                    shop_resolve_source=runtime.shop_resolve_source,
                    circuit_break_status="closed",
                )
                return {"items": [item]}
            if self._is_recoverable_unit_failure(exc):
                error_code = self._extract_agent_failure_code(exc)
                item = self._build_recoverable_unit_failed_item(
                    runtime=unit_runtime,
                    plan_unit=plan_unit,
                    error_code=error_code,
                    error=str(exc),
                    account_id_status=account_id_status,
                )
                await self._persist_payload(
                    session_factory=session_factory,
                    runtime=unit_runtime,
                    metric_date=plan_unit.metric_date,
                    payload=item,
                )
                observe_shop_dashboard_collection(
                    source="browser_agent",
                    status="failed",
                    duration_seconds=time.perf_counter() - started_at,
                    shop_mode=runtime.shop_mode,
                    shop_resolve_source=runtime.shop_resolve_source,
                    circuit_break_status="closed",
                )
                return {"items": [item]}
            observe_shop_dashboard_collection(
                source=source,
                status=status,
                duration_seconds=time.perf_counter() - started_at,
                shop_mode=runtime.shop_mode,
                shop_resolve_source=runtime.shop_resolve_source,
                circuit_break_status="closed",
            )
            raise
        finally:
            helper.release_lock(business_key, token)

    async def _prepare_agent_recipe_context(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        plan_units: list[CollectionPlanUnit],
        shop_count: int,
        session_factory: SessionFactory,
    ) -> tuple[ShopDashboardRuntimeConfig, _BatchAgentContext]:
        extra_config = dict(runtime.extra_config or {})
        lifecycle_single_reason = self._agent_lifecycle_single_shop_reason(extra_config)
        if lifecycle_single_reason and shop_count != 1:
            raise ScrapingFailedException(
                lifecycle_single_reason,
                error_data={
                    "reason": lifecycle_single_reason,
                    "shop_count": shop_count,
                    "planned_units": len(plan_units),
                },
            )
        if shop_count <= 1:
            return runtime, _BatchAgentContext()

        recipe_ref = runtime.agent_recipe_ref
        if not isinstance(recipe_ref, dict):
            raise self._agent_batch_rejected(
                reason="agent_recipe_missing_for_batch",
                shop_count=shop_count,
                recipe_ref=None,
            )
        namespace, key = self._recipe_ref_namespace_key(recipe_ref)
        if not namespace or not key:
            raise self._agent_batch_rejected(
                reason="agent_recipe_missing_for_batch",
                shop_count=shop_count,
                recipe_ref=recipe_ref,
            )

        async with session_factory() as db_session:
            repository = AgentRecipeRepository(db_session)
            version = self._recipe_ref_version(recipe_ref)
            stable_recipe = (
                await repository.get_stable_active_version(namespace, key, version)
                if version is not None
                else await repository.get_stable_active(namespace, key)
            )
            if version is None and stable_recipe is not None:
                try:
                    validate_stable_recipe(
                        Recipe.model_validate(
                            _runtime_recipe_payload_from_model(stable_recipe)
                        )
                    )
                except (ValidationError, RecipeValidationError, ValueError):
                    stable_recipe = await self._find_valid_stable_recipe(
                        repository,
                        namespace,
                        key,
                    )
            if stable_recipe is None:
                active_recipe = (
                    await repository.get_active_version(namespace, key, version)
                    if version is not None
                    else await repository.get_active(namespace, key)
                )
                versions = []
                if active_recipe is None:
                    versions = await repository.list_versions(namespace, key)
                reason = (
                    "agent_recipe_missing_for_batch"
                    if active_recipe is None and not versions
                    else "agent_recipe_not_stable_for_batch"
                )
                raise self._agent_batch_rejected(
                    reason=reason,
                    shop_count=shop_count,
                    recipe_ref=recipe_ref,
                )
            if is_shop_score_recipe(stable_recipe.namespace, stable_recipe.key):
                try:
                    validate_stable_recipe(
                        Recipe.model_validate(
                            _runtime_recipe_payload_from_model(stable_recipe)
                        )
                    )
                except (ValidationError, RecipeValidationError, ValueError) as exc:
                    raise self._agent_batch_rejected(
                        reason=str(exc),
                        shop_count=shop_count,
                        recipe_ref=recipe_ref,
                    ) from exc

        extra_config["agent_recovery_enabled"] = False
        extra_config["agent_batch_mode"] = True
        extra_config["agent_recipe_inline"] = _recipe_payload_from_model(stable_recipe)
        return replace(runtime, extra_config=extra_config), _BatchAgentContext(
            enabled=True,
            recipe_id=stable_recipe.id,
            recipe_version=stable_recipe.version,
            recipe_stability=stable_recipe.stability,
        )

    async def _find_valid_stable_recipe(
        self,
        repository: AgentRecipeRepository,
        namespace: str,
        key: str,
    ):
        recipes = await repository.list_versions(namespace, key)
        for recipe in recipes:
            if recipe.status != "active" or recipe.stability != "stable":
                continue
            try:
                validate_stable_recipe(
                    Recipe.model_validate(_runtime_recipe_payload_from_model(recipe))
                )
            except (ValidationError, RecipeValidationError, ValueError):
                continue
            return recipe
        return None

    def _agent_lifecycle_single_shop_reason(
        self,
        extra_config: dict[str, Any],
    ) -> str:
        if extra_config.get("agent_recipe_validation") is True:
            return "agent_recipe_validation_requires_single_shop"
        if extra_config.get("agent_recipe_recovery") is True:
            return "agent_recipe_recovery_requires_single_shop"
        if extra_config.get("agent_discovery") is True:
            return "agent_discovery_requires_single_shop"
        return ""

    def _recipe_ref_namespace_key(self, recipe_ref: dict[str, Any]) -> tuple[str, str]:
        namespace = str(recipe_ref.get("namespace") or "").strip()
        key = str(recipe_ref.get("key") or "").strip()
        return namespace, key

    def _recipe_ref_version(self, recipe_ref: dict[str, Any]) -> int | None:
        value = recipe_ref.get("version")
        if value is None:
            return None
        try:
            version = int(value)
        except (TypeError, ValueError):
            return None
        return version if version > 0 else None

    def _agent_batch_rejected(
        self,
        *,
        reason: str,
        shop_count: int,
        recipe_ref: dict[str, Any] | None,
    ) -> ScrapingFailedException:
        return ScrapingFailedException(
            reason,
            error_data={
                "reason": reason,
                "shop_count": shop_count,
                "recipe_ref": dict(recipe_ref or {}),
            },
        )

    def _build_agent_recipe_failed_item(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        plan_unit: CollectionPlanUnit,
        error_code: str,
        error: str,
        recipe_status: str,
        recipe_stability: str | None,
    ) -> dict[str, Any]:
        item = {
            "status": "failed",
            "reason": "agent_recipe_failed",
            "metric_date": plan_unit.metric_date,
            "shop_id": runtime.shop_id,
            "target_shop_id": plan_unit.shop_id,
            "actual_shop_id": None,
            "mismatch_status": "unknown",
            "rule_id": runtime.rule_id,
            "execution_id": runtime.execution_id,
            "retry_count": 0,
            "agent_trace": [
                {
                    "stage": "browser_agent",
                    "status": "failed",
                    "error": error_code,
                }
            ],
            "error_code": error_code,
            "recommended_next_step": "single_shop_recovery",
            "recipe_status": recipe_status,
        }
        if recipe_stability:
            item["recipe_stability"] = recipe_stability
        if error:
            item["error"] = error
        return item

    async def _mark_batch_recipe_degraded(
        self,
        *,
        context: _BatchAgentContext,
        reason: str,
        session_factory: SessionFactory,
    ) -> None:
        if context.degraded:
            return
        async with context.lock:
            if context.degraded:
                return
            if context.recipe_id is not None and context.recipe_version is not None:
                async with session_factory() as db_session:
                    repository = AgentRecipeRepository(db_session)
                    await repository.mark_degraded(
                        recipe_id=context.recipe_id,
                        expected_version=context.recipe_version,
                        reason=reason,
                    )
                    await db_session.commit()
            context.degraded = True
            context.degraded_reason = reason
            context.recipe_stability = "candidate"

    def _is_agent_recipe_failure(self, exc: Exception) -> bool:
        return self._extract_agent_failure_code(exc) in {
            "observation_empty",
            "assertion_failed",
            "browser_agent_output_missing_required_fields",
            "browser_agent_output_invalid_score_field",
        }

    def _is_recoverable_unit_failure(self, exc: Exception) -> bool:
        if isinstance(exc, DataIncompleteError):
            return True
        return self._extract_agent_failure_code(exc) in {
            "timeout",
            "observation_empty",
            "assertion_failed",
            "browser_agent_output_missing_required_fields",
            "browser_agent_output_invalid_score_field",
        }

    def _build_recoverable_unit_failed_item(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        plan_unit: CollectionPlanUnit,
        error_code: str,
        error: str,
        account_id_status: str,
    ) -> dict[str, Any]:
        return {
            "status": "failed",
            "source": "browser_agent",
            "reason": "data_incomplete",
            "metric_date": plan_unit.metric_date,
            "shop_id": runtime.shop_id,
            "target_shop_id": plan_unit.shop_id,
            "actual_shop_id": None,
            "mismatch_status": "unknown",
            "rule_id": runtime.rule_id,
            "execution_id": runtime.execution_id,
            "retry_count": 0,
            "agent_trace": [
                {
                    "stage": "browser_agent",
                    "status": "failed",
                    "error": error_code,
                }
            ],
            "error_code": error_code,
            "error": error,
            "recommended_next_step": "single_shop_recovery",
            "account_id_status": account_id_status,
        }

    def _extract_agent_failure_code(self, exc: Exception) -> str:
        error_data = getattr(exc, "error_data", None)
        if isinstance(error_data, dict):
            for key in ("failure_kind", "error_code", "code"):
                value = str(error_data.get(key) or "").strip()
                if value:
                    return value
        message = str(exc).strip()
        for prefix in (
            "observation_empty",
            "assertion_failed",
            "browser_agent_output_missing_required_fields",
            "browser_agent_output_invalid_score_field",
        ):
            if message.startswith(prefix) or prefix in message:
                return prefix
        return message.split(":", 1)[0].strip() or type(exc).__name__

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
        primary_error = ""
        for item in failed_items:
            reason = str(item.get("reason") or "").strip()
            error_code = str(item.get("error_code") or "").strip()
            error = str(item.get("error") or "").strip()
            if error_code:
                error_detail = (
                    f"{error_code}: {error}"
                    if error and error != error_code
                    else error_code
                )
                primary_error = f"{reason}: {error_detail}" if reason else error_detail
                break
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
        runtime: ShopDashboardRuntimeConfig,
        metric_date: str,
        plan_unit: Any | None = None,
        lock_manager: Any,
        state_store: Any,
        login_state_manager: Any,
    ) -> dict[str, Any]:
        return self.executor.collect_one_day(
            runtime=runtime,
            metric_date=metric_date,
            plan_unit=plan_unit,
            lock_manager=lock_manager,
            state_store=state_store,
            login_state_manager=login_state_manager,
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

    async def _persist_payload(
        self,
        *,
        session_factory: SessionFactory,
        runtime: ShopDashboardRuntimeConfig,
        metric_date: str,
        payload: Any,
    ) -> None:
        if not isinstance(payload, dict):
            return
        async with session_factory() as persist_session:
            await self.result_persister.persist(
                session=persist_session,
                runtime=runtime,
                metric_date=metric_date,
                payload=payload,
            )

    def _is_success_payload(self, payload: dict[str, Any]) -> bool:
        return str(payload.get("status", "success")).strip().lower() == "success"

    async def _collect_unit_payload(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        metric_date: str,
        plan_unit: Any | None = None,
        lock_manager: Any,
        state_store: Any,
        login_state_manager: Any,
        session_factory: SessionFactory,
    ) -> dict[str, Any]:
        stage_runtime = await self._load_browser_agent_recipe(
            runtime=runtime,
            session_factory=session_factory,
        )
        return await asyncio.to_thread(
            self._collect_one_unit_payload,
            runtime=stage_runtime,
            metric_date=metric_date,
            plan_unit=plan_unit,
            lock_manager=lock_manager,
            state_store=state_store,
            login_state_manager=login_state_manager,
        )

    async def _load_browser_agent_recipe(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        session_factory: SessionFactory,
    ) -> ShopDashboardRuntimeConfig:
        extra_config = dict(runtime.extra_config or {})
        if isinstance(extra_config.get("agent_recipe_inline"), dict):
            return runtime
        recipe_ref = runtime.agent_recipe_ref
        if not isinstance(recipe_ref, dict) or isinstance(
            recipe_ref.get("recipe"), dict
        ):
            return runtime
        async with session_factory() as db_session:
            recipe = await load_agent_recipe_from_db(db_session, recipe_ref)
        if recipe is None:
            return runtime
        extra_config["agent_recipe_inline"] = (
            _recipe_payload_from_model(recipe)
            if hasattr(recipe, "entrypoint")
            else dict(recipe)
        )
        return replace(runtime, extra_config=extra_config)

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
        redis_client: RedisClient,
        account_id: str,
        shop_id: str,
    ) -> bool:
        circuit_key = redis_keys.shop_dashboard_shop_mismatch_circuit(
            account_id=account_id,
            shop_id=shop_id,
        )
        if self._is_local_circuit_open(circuit_key=circuit_key):
            return True
        try:
            value = redis_client.get(circuit_key)
        except Exception as exc:
            self._log_local_mismatch_fallback(
                operation="is_circuit_open",
                error=exc,
            )
            return self._is_local_circuit_open(circuit_key=circuit_key)
        return value not in {None, "", "0", 0, False}

    def _record_shop_mismatch_failure(
        self,
        *,
        redis_client: RedisClient,
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
        try:
            result = redis_client.eval(
                self._SHOP_MISMATCH_RECORD_SCRIPT,
                2,
                fail_count_key,
                circuit_key,
                window_seconds,
                threshold,
                circuit_open_seconds,
            )
            if isinstance(result, (list, tuple)) and len(result) >= 2:
                count = int(result[0] or 0)
                circuit_open = bool(int(result[1] or 0))
            else:
                count = int(result or 0)
                circuit_open = count >= threshold
            if count <= 0:
                raise ValueError("shop mismatch eval returned non-positive count")
            return {"count": count, "circuit_open": circuit_open}
        except Exception as exc:
            self._log_local_mismatch_fallback(
                operation="record_failure_eval",
                error=exc,
            )

        try:
            pipeline = redis_client.pipeline(transaction=True)
            pipeline.incr(fail_count_key)
            pipeline.expire(fail_count_key, window_seconds)
            result = pipeline.execute()
            count = int(result[0] or 0)
            circuit_open = count >= threshold
            if circuit_open:
                redis_client.set(circuit_key, "1", ex=circuit_open_seconds)
            return {"count": count, "circuit_open": circuit_open}
        except Exception as exc:
            self._log_local_mismatch_fallback(
                operation="record_failure_pipeline",
                error=exc,
            )

        self._log_local_mismatch_fallback(operation="record_failure")
        return self._record_local_shop_mismatch_failure(
            fail_count_key=fail_count_key,
            circuit_key=circuit_key,
            window_seconds=window_seconds,
            threshold=threshold,
            circuit_open_seconds=circuit_open_seconds,
        )

    def _clear_shop_mismatch_failure(
        self,
        *,
        redis_client: RedisClient,
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
        try:
            redis_client.delete(fail_count_key, circuit_key)
            self._clear_local_shop_mismatch_failure(
                fail_count_key=fail_count_key,
                circuit_key=circuit_key,
            )
            return
        except Exception:
            self._log_local_mismatch_fallback(operation="clear_failure")
        self._clear_local_shop_mismatch_failure(
            fail_count_key=fail_count_key,
            circuit_key=circuit_key,
        )

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

    def _record_local_shop_mismatch_failure(
        self,
        *,
        fail_count_key: str,
        circuit_key: str,
        window_seconds: int,
        threshold: int,
        circuit_open_seconds: int,
    ) -> dict[str, Any]:
        now = time.monotonic()
        cached = self._local_shop_mismatch_failures.get(fail_count_key)
        count = 1
        if cached is not None and cached[1] > now:
            count = int(cached[0]) + 1
        self._local_shop_mismatch_failures[fail_count_key] = (
            count,
            now + float(window_seconds),
        )
        circuit_open = count >= threshold
        if circuit_open:
            self._local_shop_mismatch_circuits[circuit_key] = now + float(
                circuit_open_seconds
            )
        return {"count": count, "circuit_open": circuit_open}

    def _is_local_circuit_open(self, *, circuit_key: str) -> bool:
        expires_at = self._local_shop_mismatch_circuits.get(circuit_key)
        if expires_at is None:
            return False
        if expires_at <= time.monotonic():
            self._local_shop_mismatch_circuits.pop(circuit_key, None)
            return False
        return True

    def _clear_local_shop_mismatch_failure(
        self,
        *,
        fail_count_key: str,
        circuit_key: str,
    ) -> None:
        self._local_shop_mismatch_failures.pop(fail_count_key, None)
        self._local_shop_mismatch_circuits.pop(circuit_key, None)

    def _log_local_mismatch_fallback(
        self,
        *,
        operation: str,
        error: Exception | None = None,
    ) -> None:
        if self._local_mismatch_warning_logged:
            return
        self._local_mismatch_warning_logged = True
        if error is None:
            logger.warning(
                "shop mismatch guard degraded to process-local best effort operation=%s",
                operation,
            )
            return
        logger.warning(
            "shop mismatch guard degraded to process-local best effort operation=%s error=%s",
            operation,
            error,
        )

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

    def _resolve_redis_client(self, redis_client: Any | None) -> RedisClient:
        return resolve_collection_redis_client(
            redis_client,
            component="collection_usecase",
            logger=logger,
        )
