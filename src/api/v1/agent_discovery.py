from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from src.responses.base import Response

router = APIRouter(prefix="/agent-discovery", tags=["agent-discovery"])

_RUN_EVENTS: dict[str, list[dict[str, Any]]] = {}


class AgentDiscoveryRequest(BaseModel):
    goal: str = Field(..., min_length=1)
    entrypoint_url: str = Field(..., min_length=1)
    namespace_hint: str | None = None
    key_hint: str | None = None
    max_steps: int | None = Field(default=None, ge=1, le=100)


@router.post("", response_model=Response[dict[str, Any]])
async def trigger_agent_discovery(
    payload: AgentDiscoveryRequest,
) -> Response[dict[str, Any]]:
    run_id = uuid4().hex
    event = _event(
        run_id=run_id,
        sequence=1,
        event_type="run_started",
        current_url=payload.entrypoint_url,
        page_title="",
        screenshot_artifact_id=None,
        status="queued",
        message="discovery queued",
    )
    _RUN_EVENTS[run_id] = [event]
    _publish_discovery_task(run_id=run_id, payload=payload)
    return Response.success(
        data={
            "run_id": run_id,
            "status": "queued",
            "event_sequence": 1,
        }
    )


@router.websocket("/{run_id}/events")
async def stream_agent_discovery_events(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    try:
        events = list(_RUN_EVENTS.get(run_id, []))
        for event in events:
            await websocket.send_json(event)
        if not events:
            await websocket.send_json(
                _event(
                    run_id=run_id,
                    sequence=1,
                    event_type="run_failed",
                    current_url="",
                    page_title="",
                    screenshot_artifact_id=None,
                    status="failed",
                    message="discovery run not found",
                )
            )
    except WebSocketDisconnect:
        return
    finally:
        await websocket.close()


def append_discovery_event(run_id: str, event: dict[str, Any]) -> dict[str, Any]:
    events = _RUN_EVENTS.setdefault(run_id, [])
    next_event = _event(
        run_id=run_id,
        sequence=len(events) + 1,
        event_type=str(event.get("event_type") or ""),
        current_url=str(event.get("current_url") or ""),
        page_title=str(event.get("page_title") or ""),
        screenshot_artifact_id=event.get("screenshot_artifact_id"),
        status=str(event.get("status") or ""),
        message=str(event.get("message") or ""),
    )
    events.append(next_event)
    return next_event


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
            goal=payload.goal,
            entrypoint_url=payload.entrypoint_url,
            namespace_hint=payload.namespace_hint,
            key_hint=payload.key_hint,
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
