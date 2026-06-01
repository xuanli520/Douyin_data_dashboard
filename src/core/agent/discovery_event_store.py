from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from typing import Any

from redis import Redis
from starlette.websockets import WebSocketDisconnect

from src.config import get_settings

_RUN_EVENTS: dict[str, list[dict[str, Any]]] = {}


class DiscoveryEventStore:
    def __init__(
        self,
        *,
        redis_client: Any | None = None,
        prefix: str = "agent_discovery",
        ttl_seconds: int = 86400,
    ) -> None:
        self._redis_client = redis_client
        self._prefix = str(prefix or "agent_discovery").strip(":")
        self._redis_disabled = False
        self._ttl_seconds = ttl_seconds

    def append(self, run_id: str, event: dict[str, Any] | Any) -> dict[str, Any]:
        payload = (
            event.model_dump(mode="json")
            if hasattr(event, "model_dump")
            else dict(event)
        )
        client = self._client()
        if client is None:
            events = _RUN_EVENTS.setdefault(self._memory_key(run_id), [])
            next_event = _public_event(
                run_id=run_id,
                sequence=len(events) + 1,
                event=payload,
            )
            events.append(next_event)
            return next_event

        sequence = int(client.incr(self._sequence_key(run_id)))
        next_event = _public_event(run_id=run_id, sequence=sequence, event=payload)
        encoded = json.dumps(next_event, ensure_ascii=False)
        try:
            pipeline = client.pipeline()
            pipeline.rpush(self._events_key(run_id), encoded)
            pipeline.expire(self._events_key(run_id), self._ttl_seconds)
            pipeline.expire(self._sequence_key(run_id), self._ttl_seconds)
            pipeline.publish(self._channel(run_id), encoded)
            pipeline.execute()
        except Exception:
            client.rpush(self._events_key(run_id), encoded)
            client.expire(self._events_key(run_id), self._ttl_seconds)
            client.expire(self._sequence_key(run_id), self._ttl_seconds)
            client.publish(self._channel(run_id), encoded)
        return next_event

    def list(self, run_id: str, *, after_sequence: int = 0) -> list[dict[str, Any]]:
        client = self._client()
        if client is None:
            return [
                event
                for event in _RUN_EVENTS.get(self._memory_key(run_id), [])
                if int(event.get("sequence") or 0) > after_sequence
            ]
        try:
            raw_events = client.lrange(self._events_key(run_id), 0, -1)
        except Exception:
            return []
        events: list[dict[str, Any]] = []
        for raw_event in raw_events:
            try:
                event = json.loads(raw_event)
            except (TypeError, json.JSONDecodeError):
                continue
            if int(event.get("sequence") or 0) > after_sequence:
                events.append(event)
        return events

    def pubsub(self, run_id: str) -> Any | None:
        client = self._client()
        if client is None or not hasattr(client, "pubsub"):
            return None
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(self._channel(run_id))
        return pubsub

    def _client(self) -> Any | None:
        if self._redis_disabled:
            return None
        if self._redis_client is None and "PYTEST_CURRENT_TEST" in os.environ:
            self._redis_disabled = True
            return None
        if self._redis_client is None:
            try:
                settings = get_settings().cache
                self._redis_client = Redis(
                    host=settings.host,
                    port=settings.port,
                    db=settings.db,
                    password=settings.password,
                    encoding=settings.encoding,
                    decode_responses=settings.decode_responses,
                    socket_timeout=min(settings.socket_timeout, 1),
                    socket_connect_timeout=min(settings.socket_connect_timeout, 1),
                    retry_on_timeout=False,
                )
                ping = getattr(self._redis_client, "ping", None)
                if callable(ping):
                    ping()
            except Exception:
                self._redis_disabled = True
                return None
        required = ("incr", "rpush", "lrange", "publish")
        if not all(hasattr(self._redis_client, item) for item in required):
            self._redis_disabled = True
            return None
        return self._redis_client

    def _memory_key(self, run_id: str) -> str:
        return f"{self._prefix}:{run_id}"

    def _events_key(self, run_id: str) -> str:
        return f"{self._prefix}:{run_id}:events"

    def _sequence_key(self, run_id: str) -> str:
        return f"{self._prefix}:{run_id}:sequence"

    def _channel(self, run_id: str) -> str:
        return f"{self._prefix}:{run_id}:pubsub"


def terminal_event(event: dict[str, Any]) -> bool:
    return event.get("event_type") == "run_finished"


async def stream_events(
    *,
    websocket: Any,
    store: DiscoveryEventStore,
    run_id: str,
    missing_event: dict[str, Any],
) -> None:
    pubsub = store.pubsub(run_id)
    last_sequence = 0
    try:
        events = store.list(run_id)
        if not events:
            await websocket.send_json(missing_event)
            await websocket.close()
            return
        while True:
            events = store.list(run_id, after_sequence=last_sequence)
            for event in events:
                await websocket.send_json(event)
                last_sequence = max(last_sequence, int(event.get("sequence") or 0))
                if terminal_event(event):
                    await websocket.close()
                    return
            if pubsub is None:
                await asyncio.sleep(1)
                continue
            message = await asyncio.to_thread(pubsub.get_message, timeout=1)
            if message is None:
                continue
    except WebSocketDisconnect:
        return
    finally:
        if pubsub is not None:
            pubsub.close()


def _public_event(
    *,
    run_id: str,
    sequence: int,
    event: dict[str, Any],
) -> dict[str, Any]:
    created_at = event.get("created_at") or datetime.now(tz=UTC).isoformat()
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    return {
        "run_id": run_id,
        "sequence": sequence,
        "event_type": str(event.get("event_type") or ""),
        "current_url": str(event.get("current_url") or ""),
        "page_title": str(event.get("page_title") or ""),
        "screenshot_artifact_id": event.get("screenshot_artifact_id"),
        "status": str(event.get("status") or ""),
        "message": str(event.get("message") or ""),
        "created_at": str(created_at),
    }
