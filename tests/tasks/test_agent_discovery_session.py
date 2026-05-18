from types import SimpleNamespace

from src.tasks.collection import douyin_shop_discovery as module


def test_run_discovery_passes_run_id_to_playwright_driver(monkeypatch):
    drivers = []

    class _Driver:
        def __init__(self, **kwargs):
            drivers.append(kwargs)

        def open(self, *_args, **_kwargs):
            return None

        def close(self):
            return None

    class _Agent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self, **_kwargs):
            return SimpleNamespace(model_dump=lambda mode: {"status": "failed"})

    monkeypatch.setattr(module, "PlaywrightCLIDriver", _Driver)
    monkeypatch.setattr(module, "ReActDiscoveryAgent", _Agent)

    module._run_discovery(
        run_id="run-1",
        goal="goal",
        entrypoint_url="https://fxg.jinritemai.com",
        namespace_hint=None,
        key_hint=None,
        max_steps=1,
        settings=_settings(),
    )

    assert drivers[0]["session_id"] == "run-1"


def test_discovery_replay_passes_context_session_to_playwright_driver(monkeypatch):
    drivers = []

    class _Driver:
        def __init__(self, **kwargs):
            drivers.append(kwargs)

    class _Crawler:
        def __init__(self, driver):
            self.driver = driver

        def run(self, recipe, context):
            return {"recipe": recipe.key, "session_id": context.session_id}

    monkeypatch.setattr(module, "PlaywrightCLIDriver", _Driver)
    monkeypatch.setattr(module, "AgentCrawler", _Crawler)

    result = module._DiscoveryReplayCrawler(
        run_id="run-1",
        settings=_settings(),
    ).run(
        _recipe(),
        context={"session_id": "run-1-replay"},
    )

    assert result == {"recipe": "k", "session_id": "run-1-replay"}
    assert drivers[0]["session_id"] == "run-1-replay"


def _settings():
    return SimpleNamespace(
        agent_artifact_dir=".runtime/artifacts",
        agent_browser_headed=False,
        agent_allowed_origins=["https://fxg.jinritemai.com"],
        agent_max_steps=1,
        llm_endpoint=None,
        llm_model=None,
        llm_provider="claude",
        llm_timeout_seconds=1,
    )


def _recipe():
    return {
        "namespace": "n",
        "key": "k",
        "entrypoint": {"url": "https://fxg.jinritemai.com"},
        "steps": [],
        "observations": {},
        "assertions": [],
        "security_policy": {"allowed_origins": ["https://fxg.jinritemai.com"]},
    }
