from __future__ import annotations

from typing import Any

from src.api.v1.agent_discovery import append_discovery_event
from src.tasks.base import TaskStatusMixin
from src.tasks.funboost_compat import boost
from src.tasks.params import CollectionTaskParams


@boost(
    CollectionTaskParams(
        queue_name="collection_shop_dashboard_discovery",
        consumer_override_cls=TaskStatusMixin,
    )
)
def run_agent_discovery(
    *,
    run_id: str,
    goal: str,
    entrypoint_url: str,
    namespace_hint: str | None = None,
    key_hint: str | None = None,
    max_steps: int | None = None,
) -> dict[str, Any]:
    _ = (goal, entrypoint_url, namespace_hint, key_hint, max_steps)
    append_discovery_event(
        run_id,
        {
            "event_type": "run_finished",
            "status": "queued",
            "message": "discovery worker accepted run",
        },
    )
    return {"status": "queued", "run_id": run_id}
