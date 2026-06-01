from __future__ import annotations

from typing import Any

from src import session as session_module
from src.cache import resolve_sync_redis_client
from src.config import get_settings
from src.core.agent.drivers import PlaywrightCLIDriver
from src.core.agent.login import HumanInputBroker
from src.core.agent.login import LoginSession
from src.scrapers.shop_dashboard.login_state_manager import LoginStateManager
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore
from src.tasks.base import TaskStatusMixin
from src.tasks.funboost_compat import boost
from src.tasks.params import CollectionTaskParams


@boost(
    CollectionTaskParams(
        queue_name="collection_shop_dashboard_login",
        consumer_override_cls=TaskStatusMixin,
        qps=0.2,
        concurrent_num=2,
        function_timeout=600,
        max_retry_times=0,
    )
)
def run_login_session(
    session_id: str,
    phone: str,
    account_id: str,
    data_source_id: int,
    user_id: int,
) -> dict[str, Any]:
    settings = get_settings().shop_dashboard
    try:
        redis_client = resolve_sync_redis_client()
        driver = PlaywrightCLIDriver(
            session_id=session_id,
            artifact_dir=settings.agent_artifact_dir,
        )
        state_store = SessionStateStore(base_dir=settings.runtime_state_dir)
        login_state_manager = LoginStateManager(
            state_store,
            redis_client=redis_client,
        )
        broker = HumanInputBroker(
            redis_client=redis_client,
            ttl_seconds=settings.agent_login_session_ttl_seconds,
        )
        result = LoginSession(
            session_id=session_id,
            account_id=account_id,
            phone=phone,
            driver=driver,
            broker=broker,
            state_store=state_store,
            login_state_manager=login_state_manager,
            event_sink=lambda event: append_login_event(session_id, event),
            allowed_origins=list(settings.agent_allowed_origins),
            headed=bool(settings.agent_login_browser_headed),
            code_timeout_seconds=settings.agent_login_code_timeout_seconds,
            max_steps=settings.agent_login_max_steps,
            debug_events=bool(settings.agent_login_debug_events),
            state_persist_callback=lambda state: _persist_data_source_login_state(
                data_source_id=data_source_id,
                account_id=account_id,
                storage_state=state,
                user_id=user_id,
            ),
        ).run()
        return result.to_dict()
    except Exception as exc:
        message = str(exc) or type(exc).__name__
        append_login_event(
            session_id,
            {
                "event_type": "login_failed",
                "status": "failed",
                "message": message,
            },
        )
        append_login_event(
            session_id,
            {
                "event_type": "run_finished",
                "status": "failed",
                "message": message,
            },
        )
        return {
            "logged_in": False,
            "status": "failed",
            "reason": message,
            "current_url": "",
            "page_title": "",
        }


def append_login_event(session_id: str, event: dict[str, Any] | Any) -> dict[str, Any]:
    from src.api.v1.agent_login import append_login_event as append_event

    return append_event(session_id, event)


async def _persist_data_source_login_state(
    *,
    data_source_id: int,
    account_id: str,
    storage_state: dict[str, Any],
    user_id: int,
) -> None:
    from src.domains.data_source.repository import DataSourceRepository
    from src.domains.data_source.services import DataSourceService

    session_factory = session_module.async_session_factory
    if session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with session_factory() as db_session:
        service = DataSourceService(
            ds_repo=DataSourceRepository(db_session),
            session=db_session,
        )
        await service.update_shop_dashboard_login_state(
            data_source_id,
            account_id=account_id,
            storage_state=storage_state,
            user_id=user_id,
        )
