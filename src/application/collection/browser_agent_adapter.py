from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from src import session as session_module
from src.core.agent import AgentCrawler
from src.core.agent import Recipe
from src.core.agent import RunContext
from src.core.agent import RunResult
from src.core.agent.drivers import PlaywrightCLIDriver
from src.core.agent.recovery import RecoveryResult
from src.core.agent.recovery import RecoveryService
from src.domains.agent_recipe.repository import AgentRecipeRepository
from src.scrapers.shop_dashboard.exceptions import DataIncompleteError
from src.scrapers.shop_dashboard.exceptions import LoginExpiredError
from src.scrapers.shop_dashboard.exceptions import ShopDashboardScraperError
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig


@dataclass(slots=True)
class _LoadedRecipe:
    recipe: Recipe
    payload: dict[str, Any]
    recipe_id: int | None = None
    db_backed: bool = False


class BrowserAgentAdapter:
    def __init__(
        self,
        *,
        recipe_loader: Any | None = None,
        crawler_factory: Any | None = None,
        recovery_model: Any | None = None,
        recipe_version_writer: Any | None = None,
        settings: Any | None = None,
    ) -> None:
        self.recipe_loader = recipe_loader
        self.crawler_factory = crawler_factory
        self.recovery_model = recovery_model
        self.recipe_version_writer = recipe_version_writer
        self.settings = settings

    def collect(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        metric_date: str,
        state_store: Any,
        plan_unit: Any | None = None,
    ) -> dict[str, Any]:
        loaded_recipe = self._load_recipe(runtime)
        recipe = loaded_recipe.recipe
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
                "window_start": _format_optional(
                    getattr(plan_unit, "window_start", None)
                ),
                "window_end": _format_optional(getattr(plan_unit, "window_end", None)),
            },
            storage_state_path=str(storage_state_path) if storage_state_path else None,
            headed=bool(getattr(self.settings, "agent_browser_headed", False)),
        )
        crawler = self._build_crawler(storage_state_path, context=context)
        result = crawler.run(recipe, context)
        if self._is_login_failure(result):
            raise LoginExpiredError(result.failure.message)
        if not result.ok:
            recovered_payload = self._attempt_recovery(
                loaded_recipe=loaded_recipe,
                result=result,
                context=context,
                runtime=runtime,
                metric_date=metric_date,
                storage_state_path=storage_state_path,
            )
            if recovered_payload is not None:
                return recovered_payload
            failure_message = (
                result.failure.message if result.failure else "browser_agent_failed"
            )
            raise DataIncompleteError(failure_message)
        return self._build_payload(
            runtime=runtime,
            metric_date=metric_date,
            recipe=recipe,
            result=result,
            output=result.output,
        )

    def _build_payload(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        metric_date: str,
        recipe: Recipe,
        result: RunResult,
        output: dict[str, Any],
        recovery: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self._map_output(
            runtime=runtime,
            metric_date=metric_date,
            output=output,
        )
        raw = payload.get("raw")
        if not isinstance(raw, dict):
            raw = {}
        agent = {
            "recipe": {
                "namespace": recipe.namespace,
                "key": recipe.key,
                "version": recipe.version,
            },
            "status": result.status,
        }
        if recovery is not None:
            agent["recovery"] = recovery
        raw["agent"] = agent
        payload["raw"] = raw
        return payload

    def _load_recipe(self, runtime: ShopDashboardRuntimeConfig) -> _LoadedRecipe:
        recipe_ref = runtime.agent_recipe_ref
        inline_recipe = None
        if isinstance(runtime.extra_config, dict):
            inline_recipe = runtime.extra_config.get("agent_recipe_inline")
        if inline_recipe is None and isinstance(recipe_ref, dict):
            inline_recipe = recipe_ref.get("recipe")
        if isinstance(inline_recipe, dict):
            return self._loaded_recipe_from_value(inline_recipe)
        if self.recipe_loader is not None and isinstance(recipe_ref, dict):
            loaded = self.recipe_loader(recipe_ref)
            if loaded is not None:
                return self._loaded_recipe_from_value(loaded)
        if isinstance(recipe_ref, dict):
            loaded = self._load_recipe_from_db(recipe_ref)
            if loaded is not None:
                return self._loaded_recipe_from_value(loaded, db_backed=True)
        raise ShopDashboardScraperError("agent_recipe_not_configured")

    def _loaded_recipe_from_value(
        self,
        value: Any,
        *,
        db_backed: bool = False,
    ) -> _LoadedRecipe:
        payload = (
            _recipe_payload_from_model(value)
            if hasattr(value, "entrypoint")
            else dict(value)
        )
        recipe_id = _extract_int(payload.get("id") or payload.get("recipe_id"))
        recipe = self._recipe_from_payload(payload)
        stored_payload = recipe.model_dump(mode="json")
        if recipe_id is not None:
            stored_payload["id"] = recipe_id
        return _LoadedRecipe(
            recipe=recipe,
            payload=stored_payload,
            recipe_id=recipe_id,
            db_backed=db_backed,
        )

    def _recipe_from_payload(self, payload: Any) -> Recipe:
        if isinstance(payload, Recipe):
            return payload
        if hasattr(payload, "entrypoint"):
            payload = _recipe_payload_from_model(payload)
        recipe_payload = dict(payload)
        recipe_id = recipe_payload.pop("id", None) or recipe_payload.pop(
            "recipe_id", None
        )
        recipe_payload.pop("status", None)
        recipe_payload.pop("created_at", None)
        recipe_payload.pop("updated_at", None)
        if recipe_id is not None:
            metadata = dict(recipe_payload.get("metadata") or {})
            metadata.setdefault("recipe_id", recipe_id)
            recipe_payload["metadata"] = metadata
        entrypoint = recipe_payload.get("entrypoint")
        if (
            isinstance(entrypoint, dict)
            and "url_template" in entrypoint
            and "url" not in entrypoint
        ):
            entrypoint = dict(entrypoint)
            entrypoint["url"] = entrypoint.pop("url_template")
            recipe_payload["entrypoint"] = entrypoint
        security_policy = recipe_payload.get("security_policy")
        if not security_policy:
            recipe_payload["security_policy"] = {
                "allowed_origins": list(
                    getattr(self.settings, "agent_allowed_origins", [])
                )
            }
        return Recipe.model_validate(recipe_payload)

    def _load_recipe_from_db(self, recipe_ref: dict[str, Any]) -> Any | None:
        namespace = str(recipe_ref.get("namespace") or "").strip()
        key = str(recipe_ref.get("key") or "").strip()
        if not namespace or not key:
            return None
        session_factory = getattr(session_module, "async_session_factory", None)
        if session_factory is None:
            return None

        async def _load() -> Any | None:
            async with session_factory() as db_session:
                repository = AgentRecipeRepository(db_session)
                return await repository.get_active(namespace, key)

        return session_module.run_coro(_load())

    def _attempt_recovery(
        self,
        *,
        loaded_recipe: _LoadedRecipe,
        result: RunResult,
        context: RunContext,
        runtime: ShopDashboardRuntimeConfig,
        metric_date: str,
        storage_state_path: Path | None,
    ) -> dict[str, Any] | None:
        if not self._recovery_enabled(runtime):
            return None
        model = self.recovery_model or self._build_recovery_model()
        if model is None:
            return None
        replay_crawler = _RecoveryReplayCrawler(
            adapter=self,
            storage_state_path=storage_state_path,
            context=context,
        )
        recovery = RecoveryService(model, replay_crawler).recover(
            loaded_recipe.payload,
            self._failure_payload(result),
            input_data=context.input_data,
            context=context.model_dump(mode="json"),
            artifacts=self._artifact_payload(result),
        )
        if not recovery.success:
            self._mark_recipe_degraded(loaded_recipe, recovery)
            return None
        replay_result = recovery.replay.raw if recovery.replay is not None else None
        if not isinstance(replay_result, RunResult) or not replay_result.ok:
            self._mark_recipe_degraded(loaded_recipe, recovery)
            return None
        candidate_recipe = self._recipe_from_payload(recovery.candidate_recipe or {})
        next_version = self._write_recovered_recipe(loaded_recipe, recovery)
        if (
            self.recipe_version_writer is not None or loaded_recipe.db_backed
        ) and next_version is None:
            self._mark_recipe_degraded(loaded_recipe, recovery)
            return None
        if next_version is not None:
            candidate_recipe = candidate_recipe.model_copy(
                update={"version": next_version}
            )
        recovery_metadata = {
            "status": "success",
            "previous_version": loaded_recipe.recipe.version,
            "next_version": candidate_recipe.version,
            "reason": recovery.reason,
        }
        return self._build_payload(
            runtime=runtime,
            metric_date=metric_date,
            recipe=candidate_recipe,
            result=replay_result.model_copy(update={"status": "recovered"}),
            output=replay_result.output,
            recovery=recovery_metadata,
        )

    def _build_recovery_model(self) -> Any | None:
        endpoint = str(getattr(self.settings, "llm_endpoint", "") or "").strip()
        model = str(getattr(self.settings, "llm_model", "") or "").strip()
        if not endpoint or not model:
            return None
        return _ConfiguredRecoveryModel(settings=self.settings)

    def _write_recovered_recipe(
        self,
        loaded_recipe: _LoadedRecipe,
        recovery: RecoveryResult,
    ) -> int | None:
        candidate_recipe = recovery.candidate_recipe
        if not isinstance(candidate_recipe, dict):
            return None
        expected_version = loaded_recipe.recipe.version
        if self.recipe_version_writer is not None:
            written = self.recipe_version_writer(
                namespace=loaded_recipe.recipe.namespace,
                key=loaded_recipe.recipe.key,
                expected_version=expected_version,
                candidate_recipe=candidate_recipe,
                recovery=recovery,
            )
            return _extract_version(written)
        if not loaded_recipe.db_backed:
            return None
        session_factory = getattr(session_module, "async_session_factory", None)
        if session_factory is None:
            return None

        async def _write() -> int | None:
            async with session_factory() as db_session:
                repository = AgentRecipeRepository(db_session)
                current_recipe = await repository.get_active_for_update(
                    loaded_recipe.recipe.namespace,
                    loaded_recipe.recipe.key,
                )
                if current_recipe is None or current_recipe.version != expected_version:
                    if db_session.in_transaction():
                        await db_session.rollback()
                    return None
                next_recipe = await repository.create_next_version(
                    current_recipe=current_recipe,
                    data=_recipe_version_data(candidate_recipe),
                )
                await db_session.commit()
                return next_recipe.version

        return session_module.run_coro(_write())

    def _mark_recipe_degraded(
        self,
        loaded_recipe: _LoadedRecipe,
        recovery: RecoveryResult,
    ) -> None:
        if not loaded_recipe.db_backed or loaded_recipe.recipe_id is None:
            return
        session_factory = getattr(session_module, "async_session_factory", None)
        if session_factory is None:
            return

        async def _mark() -> None:
            async with session_factory() as db_session:
                repository = AgentRecipeRepository(db_session)
                await repository.mark_degraded(
                    recipe_id=loaded_recipe.recipe_id or 0,
                    expected_version=loaded_recipe.recipe.version,
                    reason=recovery.reason,
                )
                await db_session.commit()

        session_module.run_coro(_mark())

    def _failure_payload(self, result: RunResult) -> dict[str, Any]:
        if result.failure is None:
            return {"type": "unknown", "reason": "browser_agent_failed"}
        payload = result.failure.model_dump(mode="json")
        payload.setdefault("type", result.failure.kind)
        payload.setdefault("code", result.failure.kind)
        payload.setdefault("reason", result.failure.message)
        return payload

    def _artifact_payload(self, result: RunResult) -> dict[str, Any]:
        return {
            "metadata": dict(result.metadata or {}),
            "artifacts": [item.model_dump(mode="json") for item in result.artifacts],
        }

    def _recovery_enabled(self, runtime: ShopDashboardRuntimeConfig) -> bool:
        if not isinstance(runtime.extra_config, dict):
            return True
        return runtime.extra_config.get("agent_recovery_enabled") is not False

    def _is_login_failure(self, result: RunResult) -> bool:
        if result.failure is None:
            return False
        kind = str(result.failure.kind or "").strip().lower()
        return kind in {"loginexpirederror", "login_expired", "auth_required"}

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

    def _build_crawler(
        self,
        storage_state_path: Path | None,
        *,
        context: RunContext,
    ) -> Any:
        """Build a crawler bound to the current Playwright CLI session."""
        if self.crawler_factory is not None:
            return self.crawler_factory(storage_state_path, context)
        driver = PlaywrightCLIDriver(
            session_id=context.session_id,
            storage_state_path=storage_state_path,
            artifact_dir=getattr(
                self.settings, "agent_artifact_dir", ".runtime/agent_artifacts"
            ),
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
        _validate_required_output(payload)
        payload.setdefault("status", "success")
        payload.setdefault("source", "browser_agent")
        payload.setdefault("shop_id", runtime.shop_id)
        payload.setdefault("metric_date", metric_date)
        payload.setdefault("rule_id", runtime.rule_id)
        payload.setdefault("execution_id", runtime.execution_id)
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


def _validate_required_output(payload: dict[str, Any]) -> None:
    required_fields = (
        "actual_shop_id",
        "total_score",
        "product_score",
        "logistics_score",
        "service_score",
        "bad_behavior_score",
    )
    missing = [field for field in required_fields if payload.get(field) is None]
    if missing:
        raise DataIncompleteError(
            f"browser_agent_output_missing_required_fields: {', '.join(missing)}"
        )
    empty = [
        field
        for field in required_fields
        if isinstance(payload.get(field), str) and not payload[field].strip()
    ]
    if empty:
        raise DataIncompleteError(
            f"browser_agent_output_empty_required_fields: {', '.join(empty)}"
        )
    for field in required_fields[1:]:
        try:
            payload[field] = float(payload[field])
        except (TypeError, ValueError) as exc:
            raise DataIncompleteError(
                f"browser_agent_output_invalid_score_field: {field}"
            ) from exc


def _recipe_payload_from_model(value: Any) -> dict[str, Any]:
    payload = {
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
    recipe_id = getattr(value, "id", None)
    if recipe_id is not None:
        payload["id"] = recipe_id
    metadata = getattr(value, "metadata", None)
    if isinstance(metadata, dict):
        payload["metadata"] = dict(metadata)
    return payload


class _RecoveryReplayCrawler:
    def __init__(
        self,
        *,
        adapter: BrowserAgentAdapter,
        storage_state_path: Path | None,
        context: RunContext,
    ) -> None:
        self._adapter = adapter
        self._storage_state_path = storage_state_path
        self._context = context

    def run(
        self,
        recipe: dict[str, Any],
        *,
        input_data: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> RunResult:
        _ = context
        crawler = self._adapter._build_crawler(
            self._storage_state_path,
            context=self._context,
        )
        parsed_recipe = self._adapter._recipe_from_payload(recipe)
        replay_context = self._context
        if input_data is not None:
            replay_context = replay_context.model_copy(
                update={"input_data": input_data}
            )
        return crawler.run(parsed_recipe, replay_context)


class _ConfiguredRecoveryModel:
    def __init__(self, *, settings: Any, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        api_key = str(getattr(settings, "llm_api_key", "") or "").strip()
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = client or httpx.Client(headers=headers)

    def propose_recovery(
        self,
        request: Any,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        endpoint = str(getattr(self._settings, "llm_endpoint", "") or "").strip()
        model = str(getattr(self._settings, "llm_model", "") or "").strip()
        if not endpoint or not model:
            return {}
        provider = str(getattr(self._settings, "llm_provider", "claude") or "")
        timeout = int(getattr(self._settings, "llm_timeout_seconds", 120) or 120)
        payload = self._build_payload(
            provider=provider.strip().lower(),
            model=model,
            request=request,
            messages=messages,
        )
        response = self._client.post(endpoint, json=payload, timeout=timeout)
        response.raise_for_status()
        return self._parse_response(response.json())

    def _build_payload(
        self,
        *,
        provider: str,
        model: str,
        request: Any,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        if provider == "openai":
            return {
                "model": model,
                "response_format": {"type": "json_object"},
                "messages": messages,
            }
        return {
            "model": model,
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "request": request.to_dict()
                            if hasattr(request, "to_dict")
                            else request,
                            "messages": messages,
                        },
                        ensure_ascii=False,
                    ),
                }
            ],
        }

    def _parse_response(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            return {}
        if "patches" in data:
            return data
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            message = (
                choices[0].get("message") if isinstance(choices[0], dict) else None
            )
            if isinstance(message, dict):
                parsed = self._parse_json_text(message.get("content"))
                if parsed:
                    return parsed
        content = data.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                parsed = self._parse_json_text(item.get("text"))
                if parsed:
                    return parsed
        return {}

    def _parse_json_text(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, str):
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def _recipe_version_data(recipe: dict[str, Any]) -> dict[str, Any]:
    return {
        "entrypoint": dict(recipe.get("entrypoint") or {}),
        "steps": list(recipe.get("steps") or []),
        "observations": dict(recipe.get("observations") or {}),
        "assertions": list(recipe.get("assertions") or []),
        "recovery_policy": dict(recipe.get("recovery_policy") or {}),
        "security_policy": dict(recipe.get("security_policy") or {}),
    }


def _extract_version(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, dict):
        return _extract_int(value.get("version"))
    return _extract_int(getattr(value, "version", None))


def _extract_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
