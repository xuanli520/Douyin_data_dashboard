from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any
from typing import Protocol

from src.scrapers.shop_dashboard.lock_manager import LockManager
from src.scrapers.shop_dashboard.login_state_manager import LoginStateManager
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.scrapers.shop_dashboard.session_bootstrapper import SessionBootstrapper
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore
from src.shared.idempotency import FunboostIdempotencyHelper


class RateLimiterProtocol(Protocol):
    def wait(self) -> None: ...


class CollectionExecutor(Protocol):
    def create_rate_limiter(
        self,
        policy: int | dict[str, Any] | None,
    ) -> RateLimiterProtocol: ...

    def create_idempotency_helper(
        self,
        *,
        redis_client: Any,
        task_name: str,
    ) -> FunboostIdempotencyHelper: ...

    def create_state_store(self, *, base_dir: Path) -> SessionStateStore: ...

    def materialize_runtime_storage_state(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        state_store: SessionStateStore,
    ) -> ShopDashboardRuntimeConfig: ...

    def create_lock_manager(self, *, redis_client: Any) -> LockManager: ...

    def create_login_state_manager(
        self,
        *,
        state_store: SessionStateStore,
        redis_client: Any,
    ) -> LoginStateManager: ...

    def create_bootstrapper(
        self,
        *,
        state_store: SessionStateStore,
    ) -> SessionBootstrapper: ...

    def build_business_key(
        self,
        runtime: ShopDashboardRuntimeConfig,
        metric_date: str,
        *,
        plan_unit: Any | None = None,
        queue_task_id: str | None = None,
    ) -> str: ...

    def collect_one_day(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        metric_date: str,
        lock_manager: LockManager,
        state_store: SessionStateStore,
        login_state_manager: LoginStateManager,
    ) -> dict[str, Any]: ...


class TaskModuleCollectionExecutor:
    def __init__(self) -> None:
        from src.tasks.collection import douyin_shop_dashboard as task_module

        self._task_module = task_module

    def create_rate_limiter(
        self,
        policy: int | dict[str, Any] | None,
    ) -> RateLimiterProtocol:
        rate_limiter_cls = getattr(self._task_module, "_RateLimiter")
        return rate_limiter_cls(policy)

    def create_idempotency_helper(
        self,
        *,
        redis_client: Any,
        task_name: str,
    ) -> FunboostIdempotencyHelper:
        helper_cls = getattr(
            self._task_module,
            "FunboostIdempotencyHelper",
            FunboostIdempotencyHelper,
        )
        return helper_cls(redis_client=redis_client, task_name=task_name)

    def create_state_store(self, *, base_dir: Path) -> SessionStateStore:
        state_store_cls = getattr(
            self._task_module, "SessionStateStore", SessionStateStore
        )
        return state_store_cls(base_dir=base_dir)

    def materialize_runtime_storage_state(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        state_store: SessionStateStore,
    ) -> ShopDashboardRuntimeConfig:
        materialize = getattr(
            self._task_module,
            "_materialize_runtime_storage_state",
            None,
        )
        if callable(materialize):
            return materialize(runtime, state_store)
        return runtime

    def create_lock_manager(self, *, redis_client: Any) -> LockManager:
        lock_manager_cls = getattr(self._task_module, "LockManager", LockManager)
        return lock_manager_cls(redis_client=redis_client)

    def create_login_state_manager(
        self,
        *,
        state_store: SessionStateStore,
        redis_client: Any,
    ) -> LoginStateManager:
        login_state_manager_cls = getattr(
            self._task_module,
            "LoginStateManager",
            LoginStateManager,
        )
        return login_state_manager_cls(
            state_store=state_store,
            redis_client=redis_client,
        )

    def create_bootstrapper(
        self,
        *,
        state_store: SessionStateStore,
    ) -> SessionBootstrapper:
        bootstrapper_cls = getattr(
            self._task_module,
            "SessionBootstrapper",
            SessionBootstrapper,
        )
        return bootstrapper_cls(
            state_store=state_store,
        )

    def build_business_key(
        self,
        runtime: ShopDashboardRuntimeConfig,
        metric_date: str,
        *,
        plan_unit: Any | None = None,
        queue_task_id: str | None = None,
    ) -> str:
        build_business_key = getattr(self._task_module, "_build_business_key")
        return str(
            build_business_key(
                runtime,
                metric_date,
                plan_unit=plan_unit,
                queue_task_id=queue_task_id,
            )
        )

    def collect_one_day(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        metric_date: str,
        lock_manager: LockManager,
        state_store: SessionStateStore,
        login_state_manager: LoginStateManager,
    ) -> dict[str, Any]:
        collect_one_day = getattr(self._task_module, "_collect_one_day")
        if _supports_shared_helpers(collect_one_day):
            return collect_one_day(
                runtime,
                metric_date,
                lock_manager=lock_manager,
                state_store=state_store,
                login_state_manager=login_state_manager,
            )
        return collect_one_day(
            runtime,
            metric_date,
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
