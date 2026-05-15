from src.core.agent.events import DiscoveryEvent
from src.core.agent.observation_sync import ObservationSync


def test_observation_sync_filters_sensitive_fields():
    sync = ObservationSync()

    event = sync.publish(
        DiscoveryEvent(
            run_id="run-1",
            event_type="page_observed",
            current_url="https://example.com/app",
            page_title="Example",
            screenshot_artifact_id="shot-1",
            status="running",
            message="page observed",
            snapshot_text="private snapshot",
            thought="private thought",
            tool_arguments={"locator": "#secret"},
            tool_result={"html": "<div>private</div>"},
        )
    )

    assert event == {
        "run_id": "run-1",
        "sequence": 1,
        "event_type": "page_observed",
        "current_url": "https://example.com/app",
        "page_title": "Example",
        "screenshot_artifact_id": "shot-1",
        "status": "running",
        "message": "page observed",
        "created_at": event["created_at"],
    }


def test_observation_sync_ignores_internal_only_events():
    sync = ObservationSync()

    event = sync.publish(
        DiscoveryEvent(
            run_id="run-1",
            event_type="llm_selected",
            message="internal",
        )
    )

    assert event is None
    assert sync.events == []


def test_observation_sync_increments_sequence_monotonically():
    sync = ObservationSync()

    first = sync.publish(
        DiscoveryEvent(run_id="run-1", event_type="run_started", message="start")
    )
    second = sync.publish(
        DiscoveryEvent(run_id="run-1", event_type="run_finished", message="end")
    )

    assert first["sequence"] == 1
    assert second["sequence"] == 2
