from types import SimpleNamespace

from src.core.agent.login import LoginResult
from src.tasks.collection import douyin_shop_login as module


def test_run_login_session_wires_dependencies(monkeypatch):
    captured = {}
    persisted = []

    class _Driver:
        def __init__(self, **kwargs):
            captured["driver"] = kwargs

    class _StateStore:
        def __init__(self, base_dir):
            captured["state_store"] = base_dir

    class _LoginStateManager:
        def __init__(self, state_store, redis_client=None):
            captured["login_state_manager"] = (state_store, redis_client)

    class _Broker:
        def __init__(self, **kwargs):
            captured["broker"] = kwargs

    class _Session:
        def __init__(self, **kwargs):
            captured["session"] = kwargs
            self.kwargs = kwargs

        def run(self):
            state = {"cookies": [], "origins": []}
            self.kwargs["state_persist_callback"](state)
            return LoginResult(True, status="succeeded", state=state)

    settings = SimpleNamespace(
        agent_artifact_dir=".runtime/artifacts",
        runtime_state_dir=".runtime/state",
        agent_login_session_ttl_seconds=900,
        agent_allowed_origins=["https://fxg.jinritemai.com"],
        agent_login_browser_headed=True,
        agent_login_code_timeout_seconds=300,
        agent_login_max_steps=20,
        agent_login_debug_events=False,
    )
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: SimpleNamespace(shop_dashboard=settings),
    )
    redis = object()
    monkeypatch.setattr(module, "resolve_sync_redis_client", lambda: redis)
    monkeypatch.setattr(module, "PlaywrightCLIDriver", _Driver)
    monkeypatch.setattr(module, "SessionStateStore", _StateStore)
    monkeypatch.setattr(module, "LoginStateManager", _LoginStateManager)
    monkeypatch.setattr(module, "HumanInputBroker", _Broker)
    monkeypatch.setattr(module, "LoginSession", _Session)
    monkeypatch.setattr(
        module,
        "_persist_data_source_login_state",
        lambda **kwargs: persisted.append(kwargs),
    )

    result = module.run_login_session(
        session_id="session-1",
        phone="13800138000",
        account_id="acct-1",
        data_source_id=7,
        user_id=1,
    )

    assert result["logged_in"] is True
    assert captured["driver"] == {
        "session_id": "session-1",
        "artifact_dir": ".runtime/artifacts",
    }
    assert captured["broker"] == {"redis_client": redis, "ttl_seconds": 900}
    assert captured["session"]["session_id"] == "session-1"
    assert captured["session"]["account_id"] == "acct-1"
    assert captured["session"]["phone"] == "13800138000"
    assert captured["session"]["headed"] is True
    assert callable(captured["session"]["state_persist_callback"])
    assert persisted == [
        {
            "data_source_id": 7,
            "account_id": "acct-1",
            "storage_state": {"cookies": [], "origins": []},
            "user_id": 1,
        }
    ]
    assert "llm_client" not in captured["session"]


def test_run_login_session_records_startup_failure(monkeypatch):
    events = []

    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: SimpleNamespace(
            shop_dashboard=SimpleNamespace(
                agent_artifact_dir=".runtime/artifacts",
                runtime_state_dir=".runtime/state",
            )
        ),
    )
    monkeypatch.setattr(
        module,
        "resolve_sync_redis_client",
        lambda: (_ for _ in ()).throw(RuntimeError("redis down")),
    )
    monkeypatch.setattr(
        module, "append_login_event", lambda _session_id, event: events.append(event)
    )

    result = module.run_login_session(
        session_id="session-2",
        phone="13800138000",
        account_id="acct-1",
        data_source_id=7,
        user_id=1,
    )

    assert result["logged_in"] is False
    assert [event["event_type"] for event in events] == [
        "login_failed",
        "run_finished",
    ]
