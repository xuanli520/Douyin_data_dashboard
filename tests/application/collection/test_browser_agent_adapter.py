from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application.collection.browser_agent_adapter import BrowserAgentAdapter
from src.core.agent.models import Failure
from src.core.agent.models import RunResult
from src.scrapers.shop_dashboard.exceptions import DataIncompleteError
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
        common_query={},
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
        "observations": {
            "total": {
                "id": "total",
                "kind": "text",
                "locator": {"kind": "css", "value": ".old-total"},
                "required": True,
            }
        },
        "assertions": [],
        "recovery_policy": {"enabled": True, "max_attempts": 1},
        "security_policy": {"allowed_origins": ["https://example.test"]},
    }


def _agent_output(**overrides):
    output = {
        "actual_shop_id": "1001",
        "total_score": 90,
        "product_score": 91,
        "logistics_score": 92,
        "service_score": 93,
        "bad_behavior_score": 94,
    }
    output.update(overrides)
    return output


def test_browser_agent_adapter_maps_crawler_output(tmp_path):
    state_store = SessionStateStore(tmp_path)
    state_store.save_playwright_state(
        "acct-1",
        {"cookies": [], "origins": []},
        "1001",
    )
    seen_paths: list[Path | None] = []
    seen_contexts = []

    class _Crawler:
        def run(self, recipe, context):
            assert recipe.key == "overview"
            assert context.storage_state_path.endswith("1001.json")
            return RunResult(
                status="succeeded",
                output=_agent_output(shop_name="name"),
            )

    def crawler_factory(path, context):
        seen_paths.append(path)
        seen_contexts.append(context)
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
    assert seen_contexts[0].session_id == "acct-1-1001-2026-03-01"


def test_browser_agent_adapter_accepts_inline_recipe(tmp_path):
    adapter = BrowserAgentAdapter(
        crawler_factory=lambda _path, _context: SimpleNamespace(
            run=lambda _recipe, _context: RunResult(
                status="succeeded",
                output=_agent_output(),
            )
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


def test_browser_agent_adapter_recovers_recipe_and_records_next_version(tmp_path):
    calls = []
    written = []

    class _Model:
        def propose_recovery(self, request, messages):
            _ = (request, messages)
            return {
                "base_version": 1,
                "confidence": 0.91,
                "reason": "replace locator",
                "patches": [
                    {
                        "op": "replace",
                        "path": "/observations/total/locator",
                        "value": {"type": "css", "value": ".new-total"},
                    }
                ],
            }

    class _FailingCrawler:
        def run(self, recipe, context):
            calls.append(
                ("failed", recipe.observations["total"].locator.value, context)
            )
            return RunResult(
                status="failed",
                failure=Failure(
                    kind="observation_empty",
                    message="missing total",
                    observation_id="total",
                    recoverable=True,
                ),
            )

    class _RecoveredCrawler:
        def run(self, recipe, context):
            calls.append(
                ("recovered", recipe.observations["total"].locator.value, context)
            )
            return RunResult(status="succeeded", output=_agent_output(total_score=95))

    crawlers = [_FailingCrawler(), _RecoveredCrawler()]

    def crawler_factory(_path, _context):
        return crawlers.pop(0)

    def recipe_version_writer(**payload):
        written.append(payload)
        return {"version": 2}

    adapter = BrowserAgentAdapter(
        recipe_loader=lambda _ref: _recipe(),
        crawler_factory=crawler_factory,
        recovery_model=_Model(),
        recipe_version_writer=recipe_version_writer,
        settings=SimpleNamespace(
            agent_browser_headed=False,
            agent_allowed_origins=["https://example.test"],
            agent_artifact_dir=str(tmp_path / "artifacts"),
        ),
    )

    payload = adapter.collect(
        runtime=_runtime(),
        metric_date="2026-03-01",
        state_store=SessionStateStore(tmp_path),
    )

    assert payload["total_score"] == 95
    assert payload["raw"]["agent"]["recipe"]["version"] == 2
    assert payload["raw"]["agent"]["recovery"] == {
        "status": "success",
        "previous_version": 1,
        "next_version": 2,
        "reason": "recovered",
    }
    assert [call[0] for call in calls] == ["failed", "recovered"]
    assert calls[1][1] == ".new-total"
    assert written[0]["expected_version"] == 1


def test_browser_agent_adapter_disables_recovery_in_batch_mode(tmp_path):
    class _Model:
        def propose_recovery(self, request, messages):
            _ = (request, messages)
            raise AssertionError("batch recovery should be disabled")

    class _FailingCrawler:
        def run(self, recipe, context):
            _ = (recipe, context)
            return RunResult(
                status="failed",
                failure=Failure(
                    kind="observation_empty",
                    message="missing total",
                    observation_id="total",
                    recoverable=True,
                ),
            )

    adapter = BrowserAgentAdapter(
        crawler_factory=lambda _path, _context: _FailingCrawler(),
        recovery_model=_Model(),
        settings=SimpleNamespace(
            agent_browser_headed=False,
            agent_allowed_origins=["https://example.test"],
            agent_artifact_dir=str(tmp_path / "artifacts"),
        ),
    )

    with pytest.raises(DataIncompleteError) as exc_info:
        adapter.collect(
            runtime=_runtime(
                {
                    "agent_batch_mode": True,
                    "agent_recipe_inline": _recipe(),
                }
            ),
            metric_date="2026-03-01",
            state_store=SessionStateStore(tmp_path),
        )

    assert exc_info.value.error_data["failure_kind"] == "observation_empty"
