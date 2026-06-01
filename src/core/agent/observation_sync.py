from __future__ import annotations

from typing import Any, Callable

from src.core.agent.events import DiscoveryEvent

VISIBLE_EVENT_TYPES = {
    "run_started",
    "page_observed",
    "tool_started",
    "tool_finished",
    "recipe_generated",
    "run_failed",
    "run_finished",
}


class ObservationSync:
    def __init__(self, sink: Callable[[dict[str, Any]], None] | None = None) -> None:
        self._sink = sink
        self._sequence = 0
        self._events: list[dict[str, Any]] = []

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def reset(self) -> None:
        self._sequence = 0
        self._events.clear()

    def publish(self, event: DiscoveryEvent | dict[str, Any]) -> dict[str, Any] | None:
        normalized = (
            event
            if isinstance(event, DiscoveryEvent)
            else DiscoveryEvent.model_validate(event)
        )
        public_event = self.to_public_event(normalized)
        if public_event is None:
            return None
        self._events.append(public_event)
        if self._sink is not None:
            self._sink(public_event)
        return public_event

    def to_public_event(self, event: DiscoveryEvent) -> dict[str, Any] | None:
        if event.event_type not in VISIBLE_EVENT_TYPES:
            return None
        self._sequence += 1
        return {
            "run_id": event.run_id,
            "sequence": self._sequence,
            "event_type": event.event_type,
            "current_url": event.current_url,
            "page_title": event.page_title,
            "screenshot_artifact_id": event.screenshot_artifact_id,
            "status": event.status,
            "message": event.message,
            "created_at": event.created_at.isoformat(),
        }
