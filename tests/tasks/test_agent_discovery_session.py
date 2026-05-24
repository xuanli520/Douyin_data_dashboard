import asyncio
from types import SimpleNamespace

from src.domains.agent_recipe.repository import AgentRecipeRepository
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore
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

    result = module._run_discovery(
        run_id="run-1",
        shop_id="shop-1",
        goal="goal",
        entrypoint_url="https://fxg.jinritemai.com",
        namespace_hint=None,
        key_hint=None,
        max_steps=1,
        settings=_settings(),
    )

    assert drivers[0]["session_id"] == "run-1"
    assert result["shop_id"] == "shop-1"


def test_discovery_replay_passes_context_session_to_playwright_driver(monkeypatch):
    drivers = []

    class _Driver:
        def __init__(self, **kwargs):
            drivers.append(kwargs)

    class _Crawler:
        def __init__(self, driver):
            self.driver = driver

        def run(self, recipe, context):
            return {
                "recipe": recipe.key,
                "session_id": context.session_id,
                "shop_id": context.input_data["shop_id"],
            }

    monkeypatch.setattr(module, "PlaywrightCLIDriver", _Driver)
    monkeypatch.setattr(module, "AgentCrawler", _Crawler)

    result = module._DiscoveryReplayCrawler(
        run_id="run-1",
        shop_id="shop-1",
        settings=_settings(),
    ).run(
        _recipe(),
        context={"session_id": "run-1-replay"},
    )

    assert result == {
        "recipe": "k",
        "session_id": "run-1-replay",
        "shop_id": "shop-1",
    }
    assert drivers[0]["session_id"] == "run-1-replay"


def test_replay_recipe_passes_shop_id_to_runner(monkeypatch):
    calls = []

    class _Runner:
        def __init__(self, crawler):
            self.crawler = crawler

        def replay(self, recipe, **kwargs):
            calls.append({"crawler": self.crawler, "recipe": recipe, **kwargs})
            return SimpleNamespace(success=True)

    monkeypatch.setattr(module, "ReplayRunner", _Runner)

    module._replay_recipe(
        run_id="run-1",
        shop_id="shop-1",
        recipe=_recipe(),
        settings=_settings(),
    )

    assert calls[0]["input_data"]["shop_id"] == "shop-1"
    assert calls[0]["context"]["shop_id"] == "shop-1"
    assert calls[0]["crawler"]._shop_id == "shop-1"


def test_discovery_storage_state_prefers_shop_state(tmp_path):
    store = SessionStateStore(tmp_path)
    account_path = store.save_playwright_state("acct-1", {"cookies": []})
    shop_path = store.save_playwright_state("acct-1", {"cookies": []}, "shop-1")
    settings = SimpleNamespace(runtime_state_dir=str(tmp_path))

    assert module._resolve_storage_state_path(settings, "acct-1", "shop-1") == shop_path
    assert module._resolve_storage_state_path(settings, "acct-1", "shop-2") == account_path


def test_write_agent_recipe_persists_candidate(test_db, monkeypatch):
    monkeypatch.setattr(
        module.session_module,
        "async_session_factory",
        test_db,
        raising=False,
    )

    written = module._write_agent_recipe(_recipe())

    async def _load():
        async with test_db() as db_session:
            return await AgentRecipeRepository(db_session).get_by_id(written["id"])

    stored = asyncio.run(_load())

    assert stored is not None
    assert stored.stability == "candidate"


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
