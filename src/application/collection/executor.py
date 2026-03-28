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
        rate_limiter_cls = _resolve_task_module_symbol(
            self._task_module,
            "_RateLimiter",
            "RateLimiter",
        )
        if not callable(rate_limiter_cls):
            raise AttributeError("missing rate limiter implementation")
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
        build_business_key = _resolve_task_module_symbol(
            self._task_module,
            "_build_business_key",
            "build_business_key",
        )
        if not callable(build_business_key):
            raise AttributeError("missing business key builder")
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
        collect_one_day = _resolve_task_module_symbol(
            self._task_module,
            "_collect_one_day",
            "collect_one_day",
        )
        if not callable(collect_one_day):
            raise AttributeError("missing collection entrypoint")
        keyword_args = {
            "lock_manager": lock_manager,
            "state_store": state_store,
            "login_state_manager": login_state_manager,
        }
        if _supports_shared_helpers(collect_one_day):
            return collect_one_day(runtime, metric_date, **keyword_args)
        if _signature_unavailable(collect_one_day):
            try:
                return collect_one_day(runtime, metric_date, **keyword_args)
            except TypeError as exc:
                if not _is_unexpected_keyword_error(exc, keyword_args):
                    raise
        return collect_one_day(runtime, metric_date)


def _supports_shared_helpers(collector: Any) -> bool:
    try:
        signature = inspect.signature(collector)
    except (TypeError, ValueError):
        return False
    parameters = signature.parameters
    if any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    ):
        return True
    required = {"lock_manager", "state_store", "login_state_manager"}
    return required.issubset(parameters.keys())


def _signature_unavailable(call: Any) -> bool:
    try:
        inspect.signature(call)
    except (TypeError, ValueError):
        return True
    return False


def _is_unexpected_keyword_error(exc: TypeError, keyword_args: dict[str, Any]) -> bool:
    message = str(exc)
    if "unexpected keyword argument" not in message:
        return False
    return any(name in message for name in keyword_args)


def _resolve_task_module_symbol(task_module: Any, *names: str) -> Any:
    for module in (task_module, _default_task_module()):
        for name in names:
            value = getattr(module, name, None)
            if value is not None:
                return value
    return None


def _default_task_module() -> Any:
    from src.tasks.collection import douyin_shop_dashboard as task_module

    return task_module
