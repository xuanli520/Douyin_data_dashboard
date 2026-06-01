from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from src.auth import User, current_user
from src.auth.permissions import ShopDashboardPermission
from src.auth.rbac import require_permissions
from src.api.v1.agent_auth import authorize_agent_websocket
from src.config import get_settings
from src.core.agent.discovery_event_store import (
    DiscoveryEventStore,
    _RUN_EVENTS as _STORE_RUN_EVENTS,
    stream_events,
)
from src.domains.agent_recipe.discovery_state import (
    inspect_discovery_storage_state_async,
    resolve_discovery_storage_state_path_async,
)
from src.domains.agent_recipe.schemas import AgentRecipeMarkStable
from src.domains.agent_recipe.services import (
    AgentRecipeService,
    get_agent_recipe_service,
)
from src.domains.agent_recipe.validation import SHOP_SCORE_RECIPE_REF
from src.domains.agent_recipe.validation import is_shop_score_recipe
from src.responses.base import Response

router = APIRouter(prefix="/agent-discovery", tags=["agent-discovery"])

_EVENT_STORE = DiscoveryEventStore()
_DISCOVERY_PERMISSION = ShopDashboardPermission.TRIGGER
_RUN_EVENTS = _STORE_RUN_EVENTS


class AgentDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shop_id: str = Field(..., min_length=1)
    account_id: str | None = Field(default=None, min_length=1, max_length=128)
    goal: str = Field(..., min_length=1)
    entrypoint_url: str = Field(..., min_length=1)
    namespace_hint: str | None = SHOP_SCORE_RECIPE_REF[0]
    key_hint: str | None = SHOP_SCORE_RECIPE_REF[1]
    max_steps: int | None = Field(default=None, ge=1, le=100)


class AgentRecipeMarkStableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(..., ge=1)


@router.post("", response_model=Response[dict[str, Any]])
async def trigger_agent_discovery(
    payload: AgentDiscoveryRequest,
    _user: User = Depends(current_user),
    _=Depends(require_permissions(_DISCOVERY_PERMISSION, bypass_superuser=True)),
) -> Response[dict[str, Any]]:
    await _ensure_discovery_login_state(payload)
    run_id = uuid4().hex
    append_discovery_event(
        run_id,
        {
            "event_type": "run_started",
            "current_url": payload.entrypoint_url,
            "status": "queued",
            "message": "discovery queued",
            "shop_id": payload.shop_id,
        },
    )
    _publish_discovery_task(run_id=run_id, payload=payload)
    return Response.success(
        data={
            "run_id": run_id,
            "status": "queued",
            "event_sequence": 1,
        }
    )


@router.get("/login-state", response_model=Response[dict[str, Any]])
async def get_agent_discovery_login_state(
    account_id: str = Query(..., min_length=1, max_length=128),
    shop_id: str | None = Query(default=None, min_length=1, max_length=128),
    _user: User = Depends(current_user),
    _=Depends(require_permissions(_DISCOVERY_PERMISSION, bypass_superuser=True)),
) -> Response[dict[str, Any]]:
    state = await inspect_discovery_storage_state_async(
        get_settings().shop_dashboard,
        account_id,
        shop_id,
    )
    return Response.success(
        data={
            "account_id": account_id,
            "shop_id": shop_id,
            **state,
        }
    )


@router.post(
    "/recipes/{recipe_id}/mark-stable",
    response_model=Response[dict[str, Any]],
)
async def mark_agent_recipe_stable(
    recipe_id: int,
    payload: AgentRecipeMarkStableRequest,
    _user: User = Depends(current_user),
    _=Depends(require_permissions(_DISCOVERY_PERMISSION, bypass_superuser=True)),
    service: AgentRecipeService = Depends(get_agent_recipe_service),
) -> Response[dict[str, Any]]:
    try:
        updated = await service.mark_stable(
            AgentRecipeMarkStable(
                recipe_id=recipe_id,
                expected_version=payload.expected_version,
            )
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="agent recipe version conflict",
        )
    return Response.success(
        data={
            "recipe_id": recipe_id,
            "status": "stable",
        }
    )


@router.get("/recipes", response_model=Response[dict[str, Any]])
async def list_agent_recipes(
    _user: User = Depends(current_user),
    _=Depends(require_permissions(_DISCOVERY_PERMISSION, bypass_superuser=True)),
    service: AgentRecipeService = Depends(get_agent_recipe_service),
) -> Response[dict[str, Any]]:
    return Response.success(data=await service.list_recipes())


@router.get("/recipes/{recipe_id}/export")
async def export_agent_recipe(
    recipe_id: int,
    _user: User = Depends(current_user),
    _=Depends(require_permissions(_DISCOVERY_PERMISSION, bypass_superuser=True)),
    service: AgentRecipeService = Depends(get_agent_recipe_service),
) -> JSONResponse:
    result = await service.export_recipe(recipe_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="agent recipe not found",
        )
    payload, filename = result
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/recipes/import",
    response_model=Response[dict[str, Any]],
)
async def import_agent_recipe(
    file: UploadFile = File(...),
    _user: User = Depends(current_user),
    _=Depends(require_permissions(_DISCOVERY_PERMISSION, bypass_superuser=True)),
    service: AgentRecipeService = Depends(get_agent_recipe_service),
) -> Response[dict[str, Any]]:
    filename = file.filename or ""
    if not filename.endswith(".agent-recipe.json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="file must be .agent-recipe.json",
        )
    try:
        recipe = await service.import_recipe(await file.read())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if recipe is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="agent recipe version already exists",
        )
    return Response.success(data=recipe.model_dump(mode="json"))


@router.websocket("/{run_id}/events")
async def stream_agent_discovery_events(
    websocket: WebSocket,
    run_id: str,
) -> None:
    if not await authorize_agent_websocket(websocket, _DISCOVERY_PERMISSION):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    await stream_events(
        websocket=websocket,
        store=_EVENT_STORE,
        run_id=run_id,
        missing_event=_event(
            run_id=run_id,
            sequence=1,
            event_type="run_failed",
            current_url="",
            page_title="",
            screenshot_artifact_id=None,
            status="failed",
            message="discovery run not found",
        ),
    )


def append_discovery_event(run_id: str, event: dict[str, Any] | Any) -> dict[str, Any]:
    return _EVENT_STORE.append(run_id, event)


def _event(
    *,
    run_id: str,
    sequence: int,
    event_type: str,
    current_url: str,
    page_title: str,
    screenshot_artifact_id: str | None,
    status: str,
    message: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "sequence": sequence,
        "event_type": event_type,
        "current_url": current_url,
        "page_title": page_title,
        "screenshot_artifact_id": screenshot_artifact_id,
        "status": status,
        "message": message,
        "created_at": datetime.now(tz=UTC).isoformat(),
    }


def _publish_discovery_task(
    *,
    run_id: str,
    payload: AgentDiscoveryRequest,
) -> None:
    try:
        from src.tasks.collection.douyin_shop_discovery import (
            run_agent_discovery,
        )

        run_agent_discovery.push(
            run_id=run_id,
            shop_id=payload.shop_id,
            account_id=payload.account_id,
            goal=payload.goal,
            entrypoint_url=payload.entrypoint_url,
            namespace_hint=payload.namespace_hint or SHOP_SCORE_RECIPE_REF[0],
            key_hint=payload.key_hint or SHOP_SCORE_RECIPE_REF[1],
            max_steps=payload.max_steps,
        )
    except Exception:
        append_discovery_event(
            run_id,
            {
                "event_type": "run_failed",
                "status": "failed",
                "message": "failed to enqueue discovery task",
            },
        )
        append_discovery_event(
            run_id,
            {
                "event_type": "run_finished",
                "status": "failed",
                "message": "failed to enqueue discovery task",
            },
        )


async def _ensure_discovery_login_state(payload: AgentDiscoveryRequest) -> None:
    namespace = payload.namespace_hint or SHOP_SCORE_RECIPE_REF[0]
    key = payload.key_hint or SHOP_SCORE_RECIPE_REF[1]
    if not is_shop_score_recipe(namespace, key):
        return
    if not payload.account_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="shop dashboard account_id is required before discovery",
        )
    storage_state_path = await resolve_discovery_storage_state_path_async(
        get_settings().shop_dashboard,
        payload.account_id,
        payload.shop_id,
    )
    if storage_state_path is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="shop dashboard login state is required before discovery",
        )
