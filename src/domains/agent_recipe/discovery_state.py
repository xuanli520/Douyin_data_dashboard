from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select

from src import session as session_module
from src.domains.data_source.models import DataSource
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore


def resolve_discovery_storage_state_path(
    settings: Any,
    account_id: str | None,
    shop_id: str | None = None,
) -> Path | None:
    normalized_account_id = str(account_id or "").strip()
    if not normalized_account_id:
        return None
    state_store = SessionStateStore(base_dir=settings.runtime_state_dir)
    normalized_shop_id = str(shop_id or "").strip()
    if normalized_shop_id:
        shop_path = state_store.playwright_state_path(
            normalized_account_id,
            normalized_shop_id,
        )
        if shop_path.exists():
            return shop_path
    path = state_store.playwright_state_path(normalized_account_id)
    if path.exists():
        return path
    return _materialize_storage_state_path(normalized_account_id, state_store)


async def resolve_discovery_storage_state_path_async(
    settings: Any,
    account_id: str | None,
    shop_id: str | None = None,
) -> Path | None:
    normalized_account_id = str(account_id or "").strip()
    if not normalized_account_id:
        return None
    state_store = SessionStateStore(base_dir=settings.runtime_state_dir)
    normalized_shop_id = str(shop_id or "").strip()
    if normalized_shop_id:
        shop_path = state_store.playwright_state_path(
            normalized_account_id,
            normalized_shop_id,
        )
        if shop_path.exists():
            return shop_path
    path = state_store.playwright_state_path(normalized_account_id)
    if path.exists():
        return path
    storage_state = await _load_data_source_storage_state_async(normalized_account_id)
    if not storage_state:
        return None
    return state_store.save_playwright_state(normalized_account_id, storage_state)


async def inspect_discovery_storage_state_async(
    settings: Any,
    account_id: str | None,
    shop_id: str | None = None,
) -> dict[str, Any]:
    normalized_account_id = str(account_id or "").strip()
    if not normalized_account_id:
        return {"available": False, "reason": "missing_account_id"}
    state_store = SessionStateStore(base_dir=settings.runtime_state_dir)
    normalized_shop_id = str(shop_id or "").strip()
    if normalized_shop_id:
        shop_path = state_store.playwright_state_path(
            normalized_account_id,
            normalized_shop_id,
        )
        if shop_path.exists():
            return {"available": True, "reason": "shop_runtime_state"}
    path = state_store.playwright_state_path(normalized_account_id)
    if path.exists():
        return {"available": True, "reason": "account_runtime_state"}
    storage_state, account_found = await _load_data_source_storage_state_result_async(
        normalized_account_id
    )
    if storage_state:
        state_store.save_playwright_state(normalized_account_id, storage_state)
        return {"available": True, "reason": "data_source_storage_state"}
    return {
        "available": False,
        "reason": "data_source_storage_state_missing"
        if account_found
        else "account_not_found",
    }


def _materialize_storage_state_path(
    account_id: str,
    state_store: SessionStateStore,
) -> Path | None:
    storage_state = _load_data_source_storage_state(account_id)
    if not storage_state:
        return None
    return state_store.save_playwright_state(account_id, storage_state)


def _load_data_source_storage_state(account_id: str) -> dict[str, Any] | None:
    session_factory = session_module.async_session_factory
    if session_factory is None:
        return None
    return session_module.run_coro(_load_data_source_storage_state_async(account_id))


async def _load_data_source_storage_state_async(
    account_id: str,
) -> dict[str, Any] | None:
    storage_state, _account_found = await _load_data_source_storage_state_result_async(
        account_id
    )
    return storage_state


async def _load_data_source_storage_state_result_async(
    account_id: str,
) -> tuple[dict[str, Any] | None, bool]:
    session_factory = session_module.async_session_factory
    if session_factory is None:
        return None, False
    async with session_factory() as db_session:
        rows = (await db_session.execute(select(DataSource))).scalars().all()
        account_found = False
        for data_source in rows:
            extra_config = data_source.extra_config
            if not isinstance(extra_config, dict):
                continue
            if not _data_source_account_matches(
                data_source.id,
                extra_config,
                account_id,
            ):
                continue
            account_found = True
            storage_state = _storage_state_from_extra_config(extra_config)
            if storage_state:
                return storage_state, account_found
    return None, account_found


def _data_source_account_matches(
    data_source_id: int | None,
    extra_config: dict[str, Any],
    account_id: str,
) -> bool:
    values: list[Any] = []
    if data_source_id is not None:
        values.append(f"data_source_{data_source_id}")
    values.append(extra_config.get("account_id"))
    meta = extra_config.get("shop_dashboard_login_state_meta")
    if isinstance(meta, dict):
        values.append(meta.get("account_id"))
    login_state = extra_config.get("shop_dashboard_login_state")
    if isinstance(login_state, dict):
        values.append(login_state.get("account_id"))
    return account_id in {str(value or "").strip() for value in values}


def _storage_state_from_extra_config(
    extra_config: dict[str, Any],
) -> dict[str, Any] | None:
    login_state = extra_config.get("shop_dashboard_login_state")
    if not isinstance(login_state, dict):
        return None
    storage_state = login_state.get("storage_state")
    return storage_state if isinstance(storage_state, dict) else None
