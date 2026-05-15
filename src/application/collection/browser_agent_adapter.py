from __future__ import annotations

from pathlib import Path
from typing import Any

from src.core.agent import AgentCrawler
from src.core.agent import Entrypoint
from src.core.agent import Recipe
from src.core.agent import RunContext
from src.core.agent import SecurityPolicy
from src.core.agent.drivers import PlaywrightCLIDriver
from src.domains.agent_recipe.repository import AgentRecipeRepository
from src.scrapers.shop_dashboard.exceptions import DataIncompleteError
from src.scrapers.shop_dashboard.exceptions import LoginExpiredError
from src.scrapers.shop_dashboard.exceptions import ShopDashboardScraperError
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig


class BrowserAgentAdapter:
    def __init__(
        self,
        *,
        recipe_loader: Any | None = None,
        crawler_factory: Any | None = None,
        settings: Any | None = None,
    ) -> None:
        self.recipe_loader = recipe_loader
        self.crawler_factory = crawler_factory
        self.settings = settings

    def collect(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        metric_date: str,
        state_store: Any,
        plan_unit: Any | None = None,
    ) -> dict[str, Any]:
        recipe = self._load_recipe(runtime)
        account_id = _resolve_account_id(runtime)
        storage_state_path = self._resolve_storage_state_path(
            state_store=state_store,
            account_id=account_id,
            runtime=runtime,
        )
        context = RunContext(
            session_id=f"{account_id}-{runtime.shop_id}-{metric_date}",
            input_data={
                "date": metric_date,
                "window_start": _format_optional(getattr(plan_unit, "window_start", None)),
                "window_end": _format_optional(getattr(plan_unit, "window_end", None)),
            },
            storage_state_path=str(storage_state_path) if storage_state_path else None,
            headed=bool(getattr(self.settings, "agent_browser_headed", False)),
        )
        crawler = self._build_crawler(storage_state_path)
        result = crawler.run(recipe, context)
        if result.failure and result.failure.kind == "LoginExpiredError":
            raise LoginExpiredError(result.failure.message)
        if not result.ok:
            failure_message = result.failure.message if result.failure else "browser_agent_failed"
            raise DataIncompleteError(failure_message)
        payload = self._map_output(
            runtime=runtime,
            metric_date=metric_date,
            output=result.output,
        )
        raw = payload.get("raw")
        if not isinstance(raw, dict):
            raw = {}
        raw["agent"] = {
            "recipe": {
                "namespace": recipe.namespace,
                "key": recipe.key,
                "version": recipe.version,
            },
            "status": result.status,
        }
        payload["raw"] = raw
        return payload

    def _load_recipe(self, runtime: ShopDashboardRuntimeConfig) -> Recipe:
        recipe_ref = runtime.agent_recipe_ref
        inline_recipe = None
        if isinstance(runtime.extra_config, dict):
            inline_recipe = runtime.extra_config.get("agent_recipe_inline")
        if inline_recipe is None and isinstance(recipe_ref, dict):
            inline_recipe = recipe_ref.get("recipe")
        if isinstance(inline_recipe, dict):
            return self._recipe_from_payload(inline_recipe)
        if self.recipe_loader is not None and isinstance(recipe_ref, dict):
            loaded = self.recipe_loader(recipe_ref)
            if loaded is not None:
                return self._recipe_from_payload(loaded)
        raise ShopDashboardScraperError("agent_recipe_not_configured")

    def _recipe_from_payload(self, payload: Any) -> Recipe:
        if isinstance(payload, Recipe):
            return payload
        if hasattr(payload, "entrypoint"):
            payload = _recipe_payload_from_model(payload)
        recipe_payload = dict(payload)
        entrypoint = recipe_payload.get("entrypoint")
        if isinstance(entrypoint, dict) and "url_template" in entrypoint and "url" not in entrypoint:
            entrypoint = dict(entrypoint)
            entrypoint["url"] = entrypoint.pop("url_template")
            recipe_payload["entrypoint"] = entrypoint
        security_policy = recipe_payload.get("security_policy")
        if not security_policy:
            recipe_payload["security_policy"] = {
                "allowed_origins": list(getattr(self.settings, "agent_allowed_origins", []))
            }
        return Recipe.model_validate(recipe_payload)

    def _resolve_storage_state_path(
        self,
        *,
        state_store: Any,
        account_id: str,
        runtime: ShopDashboardRuntimeConfig,
    ) -> Path | None:
        path_reader = getattr(state_store, "playwright_state_path", None)
        if not callable(path_reader):
            return None
        shop_path = path_reader(account_id, runtime.shop_id)
        if isinstance(shop_path, Path) and shop_path.exists():
            return shop_path
        account_path = path_reader(account_id)
        if isinstance(account_path, Path) and account_path.exists():
            return account_path
        return shop_path if isinstance(shop_path, Path) else None

    def _build_crawler(self, storage_state_path: Path | None) -> Any:
        if self.crawler_factory is not None:
            return self.crawler_factory(storage_state_path)
        driver = PlaywrightCLIDriver(
            storage_state_path=storage_state_path,
            artifact_dir=getattr(self.settings, "agent_artifact_dir", ".runtime/agent_artifacts"),
        )
        return AgentCrawler(driver)

    def _map_output(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        metric_date: str,
        output: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(output)
        payload.setdefault("status", "success")
        payload.setdefault("source", "browser_agent")
        payload.setdefault("shop_id", runtime.shop_id)
        payload.setdefault("actual_shop_id", payload.get("shop_id") or runtime.shop_id)
        payload.setdefault("metric_date", metric_date)
        payload.setdefault("rule_id", runtime.rule_id)
        payload.setdefault("execution_id", runtime.execution_id)
        payload.setdefault("total_score", 0.0)
        payload.setdefault("product_score", 0.0)
        payload.setdefault("logistics_score", 0.0)
        payload.setdefault("service_score", 0.0)
        payload.setdefault("bad_behavior_score", 0.0)
        payload.setdefault("reviews", {"summary": {}, "items": []})
        payload.setdefault("violations", {"summary": {}, "waiting_list": []})
        payload.setdefault("raw", {})
        return payload


async def load_agent_recipe_from_db(
    session: Any,
    recipe_ref: dict[str, Any],
) -> Any | None:
    namespace = str(recipe_ref.get("namespace") or "").strip()
    key = str(recipe_ref.get("key") or "").strip()
    if not namespace or not key:
        return None
    repository = AgentRecipeRepository(session)
    return await repository.get_active(namespace, key)


def _resolve_account_id(runtime: ShopDashboardRuntimeConfig) -> str:
    account_id = str(getattr(runtime, "account_id", "") or "").strip()
    if account_id:
        return account_id
    rule_id = int(getattr(runtime, "rule_id", 0) or 0)
    if rule_id > 0:
        return f"rule_{rule_id}"
    return f"unit_{runtime.shop_id}"


def _format_optional(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def _recipe_payload_from_model(value: Any) -> dict[str, Any]:
    return {
        "namespace": value.namespace,
        "key": value.key,
        "version": value.version,
        "entrypoint": dict(value.entrypoint or {}),
        "steps": list(value.steps or []),
        "observations": dict(value.observations or {}),
        "assertions": list(value.assertions or []),
        "recovery_policy": dict(value.recovery_policy or {}),
        "security_policy": dict(value.security_policy or {}),
    }
