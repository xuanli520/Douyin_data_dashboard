from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import WebSocket
from fastapi import status
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from src.auth import User
from src.auth import current_user
from src.auth.permissions import ShopDashboardPermission
from src.auth.rbac import require_permissions
from src.cache import resolve_sync_redis_client
from src.config import get_settings
from src.core.agent.discovery_event_store import DiscoveryEventStore
from src.core.agent.discovery_event_store import _RUN_EVENTS as _STORE_RUN_EVENTS
from src.core.agent.discovery_event_store import stream_events
from src.core.agent.login import HumanInputBroker
from src.core.agent.login import HumanInputBrokerUnavailable
from src.responses.base import Response
from src.api.v1.agent_auth import authorize_agent_websocket

router = APIRouter(prefix="/agent-login", tags=["agent-login"])

_EVENT_STORE = DiscoveryEventStore(prefix="agent_login")
_LOGIN_PERMISSION = ShopDashboardPermission.TRIGGER
_RUN_EVENTS = _STORE_RUN_EVENTS


class AgentLoginStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(..., min_length=5, max_length=32)
    account_id: str = Field(..., min_length=1, max_length=128)
    data_source_id: int = Field(..., gt=0)


class AgentLoginCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., pattern=r"^\d{4,6}$")


@router.post("/start", response_model=Response[dict[str, Any]])
async def start_agent_login(
    payload: AgentLoginStartRequest,
    user: User = Depends(current_user),
    _=Depends(require_permissions(_LOGIN_PERMISSION, bypass_superuser=True)),
) -> Response[dict[str, Any]]:
    session_id = uuid4().hex
    append_login_event(
        session_id,
        {
            "event_type": "queued",
            "status": "queued",
            "message": "login queued",
        },
    )
    queued = _publish_login_task(
        session_id=session_id,
        payload=payload,
        user_id=user.id,
    )
    return Response.success(
        data={
            "session_id": session_id,
            "status": "queued" if queued else "failed",
            "ws_endpoint": f"/api/v1/agent-login/{session_id}/events",
        }
    )


@router.post("/{session_id}/code", response_model=Response[dict[str, bool]])
async def submit_agent_login_code(
    session_id: str,
    payload: AgentLoginCodeRequest,
    _user: User = Depends(current_user),
    _=Depends(require_permissions(_LOGIN_PERMISSION, bypass_superuser=True)),
) -> Response[dict[str, bool]]:
    try:
        _broker().resolve(session_id, payload.code)
    except HumanInputBrokerUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    append_login_event(
        session_id,
        {
            "event_type": "code_submitted",
            "status": "submitted",
            "message": "verification code submitted",
        },
    )
    return Response.success(data={"ok": True})


@router.post("/{session_id}/cancel", response_model=Response[dict[str, bool]])
async def cancel_agent_login(
    session_id: str,
    _user: User = Depends(current_user),
    _=Depends(require_permissions(_LOGIN_PERMISSION, bypass_superuser=True)),
) -> Response[dict[str, bool]]:
    try:
        _broker().cancel(session_id)
    except HumanInputBrokerUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return Response.success(data={"ok": True})


@router.websocket("/{session_id}/events")
async def stream_agent_login_events(
    websocket: WebSocket,
    session_id: str,
) -> None:
    if not await authorize_agent_websocket(websocket, _LOGIN_PERMISSION):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    await stream_events(
        websocket=websocket,
        store=_EVENT_STORE,
        run_id=session_id,
        missing_event={
            "run_id": session_id,
            "sequence": 1,
            "event_type": "login_failed",
            "current_url": "",
            "page_title": "",
            "screenshot_artifact_id": None,
            "status": "failed",
            "message": "login session not found",
        },
    )


def append_login_event(session_id: str, event: dict[str, Any] | Any) -> dict[str, Any]:
    return _EVENT_STORE.append(session_id, event)


def _publish_login_task(
    *,
    session_id: str,
    payload: AgentLoginStartRequest,
    user_id: int,
) -> bool:
    try:
        from src.tasks.collection.douyin_shop_login import run_login_session

        run_login_session.push(
            session_id=session_id,
            phone=payload.phone,
            account_id=payload.account_id,
            data_source_id=payload.data_source_id,
            user_id=user_id,
        )
        return True
    except Exception:
        append_login_event(
            session_id,
            {
                "event_type": "login_failed",
                "status": "failed",
                "message": "failed to enqueue login task",
            },
        )
        append_login_event(
            session_id,
            {
                "event_type": "run_finished",
                "status": "failed",
                "message": "failed to enqueue login task",
            },
        )
        return False


def _broker() -> HumanInputBroker:
    settings = get_settings().shop_dashboard
    return HumanInputBroker(
        redis_client=resolve_sync_redis_client(),
        ttl_seconds=settings.agent_login_session_ttl_seconds,
    )
