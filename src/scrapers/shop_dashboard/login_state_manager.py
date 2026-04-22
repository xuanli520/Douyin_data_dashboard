from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any

from src.scrapers.shop_dashboard.session_state_store import SessionStateStore


class LoginStateManager:
    def __init__(
        self,
        state_store: SessionStateStore,
        refresh_checker: Callable[[str], Awaitable[bool] | bool] | None = None,
        redis_client: Any | None = None,
        probe_interval_days: int = 7,
        key_prefix: str = "douyin:account:login_state",
    ) -> None:
        self._state_store = state_store
        self._refresh_checker = refresh_checker
        self._redis = redis_client
        self._probe_interval_seconds = max(int(probe_interval_days), 0) * 86400
        self._key_prefix = key_prefix
        self._memory_state: dict[str, dict[str, str]] = {}

    async def check_and_refresh(self, account_id: str) -> bool:
        if not self._state_store.exists(account_id):
            await self.mark_expired(account_id, reason="state_missing")
            return False

        now = int(time.time())
        state = await self._get_state(account_id)
        last_probe_at = int(state.get("last_probe_at", "0") or "0")
        if (
            last_probe_at > 0
            and self._probe_interval_seconds > 0
            and now - last_probe_at < self._probe_interval_seconds
        ):
            return state.get("status", "active") != "expired"

        if self._refresh_checker is not None:
            refreshed = self._refresh_checker(account_id)
            if inspect.isawaitable(refreshed):
                refreshed = await refreshed
            if not bool(refreshed):
                await self.mark_expired(account_id, reason="refresh_failed")
                return False

        await self._set_state(
            account_id,
            {
                "status": "active",
                "reason": "",
                "last_probe_at": str(now),
                "updated_at": str(now),
            },
        )
        return True

    async def mark_expired(self, account_id: str, reason: str) -> None:
        now = int(time.time())
        await self._set_state(
            account_id,
            {
                "status": "expired",
                "reason": str(reason),
                "last_probe_at": str(now),
                "updated_at": str(now),
            },
        )

    def _state_key(self, account_id: str) -> str:
        return f"{self._key_prefix}:{account_id}"

    async def _get_state(self, account_id: str) -> dict[str, str]:
        if self._redis is not None:
            payload = await asyncio.to_thread(
                self._redis.hgetall,
                self._state_key(account_id),
            )
            if isinstance(payload, dict):
                return {str(k): str(v) for k, v in payload.items()}
            return {}
        return dict(self._memory_state.get(account_id, {}))

    async def _set_state(self, account_id: str, payload: dict[str, str]) -> None:
        if self._redis is not None:
            await asyncio.to_thread(
                self._redis.hset,
                self._state_key(account_id),
                mapping=payload,
            )
            return
        current = dict(self._memory_state.get(account_id, {}))
        current.update(payload)
        self._memory_state[account_id] = current
