from pathlib import Path
from types import SimpleNamespace

from src.application.collection.browser_agent_adapter import BrowserAgentAdapter
from src.core.agent.models import RunResult
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore


def _runtime(extra_config=None):
    return ShopDashboardRuntimeConfig(
        shop_mode="EXACT",
        resolved_shop_ids=["1001"],
        catalog_stale=False,
        shop_id="1001",
        cookies={},
        proxy=None,
        timeout=30,
        retry_count=0,
        rate_limit=None,
        granularity="DAY",
        time_range=None,
        incremental_mode="BY_DATE",
        backfill_last_n_days=1,
        data_latency="T+1",
        target_type="SHOP_OVERVIEW",
        metrics=[],
        dimensions=[],
        filters={},
        top_n=None,
        include_long_tail=False,
        session_level=False,
        dedupe_key=None,
        rule_id=9,
        execution_id="exec-1",
        fallback_chain=("browser_agent",),
        graphql_query=None,
        common_query={},
        token_keys=[],
        api_groups=[],
        agent_recipe_ref={"namespace": "generic", "key": "overview"},
        extra_config=extra_config or {},
        account_id="acct-1",
    )


def _recipe():
    return {
        "namespace": "generic",
        "key": "overview",
        "version": 1,
        "entrypoint": {"url": "https://example.test/app"},
        "steps": [{"id": "open", "action": "goto"}],
        "observations": {},
        "assertions": [],
        "security_policy": {"allowed_origins": ["https://example.test"]},
    }


def test_browser_agent_adapter_maps_crawler_output(tmp_path):
    state_store = SessionStateStore(tmp_path)
    state_store.save_playwright_state(
        "acct-1",
        {"cookies": [], "origins": []},
        "1001",
    )
    seen_paths: list[Path | None] = []

    class _Crawler:
        def run(self, recipe, context):
            assert recipe.key == "overview"
            assert context.storage_state_path.endswith("1001.json")
            return RunResult(
                status="succeeded",
                output={
                    "actual_shop_id": "1001",
                    "total_score": 90,
                    "shop_name": "name",
                },
            )

    def crawler_factory(path):
        seen_paths.append(path)
        return _Crawler()

    adapter = BrowserAgentAdapter(
        recipe_loader=lambda _ref: _recipe(),
        crawler_factory=crawler_factory,
        settings=SimpleNamespace(
            agent_browser_headed=False,
            agent_allowed_origins=["https://example.test"],
            agent_artifact_dir=str(tmp_path / "artifacts"),
        ),
    )

    payload = adapter.collect(
        runtime=_runtime(),
        metric_date="2026-03-01",
        state_store=state_store,
    )

    assert payload["source"] == "browser_agent"
    assert payload["total_score"] == 90
    assert payload["raw"]["agent"]["recipe"] == {
        "namespace": "generic",
        "key": "overview",
        "version": 1,
    }
    assert seen_paths == [tmp_path / "playwright_states" / "acct-1" / "1001.json"]


def test_browser_agent_adapter_accepts_inline_recipe(tmp_path):
    adapter = BrowserAgentAdapter(
        crawler_factory=lambda _path: SimpleNamespace(
            run=lambda _recipe, _context: RunResult(status="succeeded", output={})
        ),
        settings=SimpleNamespace(
            agent_browser_headed=False,
            agent_allowed_origins=["https://example.test"],
            agent_artifact_dir=str(tmp_path / "artifacts"),
        ),
    )

    payload = adapter.collect(
        runtime=_runtime({"agent_recipe_inline": _recipe()}),
        metric_date="2026-03-01",
        state_store=SessionStateStore(tmp_path),
    )

    assert payload["source"] == "browser_agent"
