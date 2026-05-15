from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.agent_discovery import _RUN_EVENTS
from src.api.v1.agent_discovery import append_discovery_event
from src.api.v1.agent_discovery import router


def test_agent_discovery_websocket_streams_sanitized_events():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    run_id = "run-1"
    _RUN_EVENTS[run_id] = []
    append_discovery_event(
        run_id,
        {
            "event_type": "page_observed",
            "current_url": "https://example.test",
            "page_title": "Example",
            "screenshot_artifact_id": "artifact-1",
            "status": "running",
            "message": "observed",
            "snapshot_text": "hidden",
        },
    )
    client = TestClient(app)

    with client.websocket_connect(f"/api/v1/agent-discovery/{run_id}/events") as ws:
        event = ws.receive_json()

    assert event["sequence"] == 1
    assert event["event_type"] == "page_observed"
    assert "snapshot_text" not in event
