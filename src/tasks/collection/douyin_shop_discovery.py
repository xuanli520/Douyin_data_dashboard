from __future__ import annotations

import json
from typing import Any

import httpx

from src import session as session_module
from src.api.v1.agent_discovery import append_discovery_event
from src.config import get_settings
from src.core.agent import AgentCrawler
from src.core.agent import Recipe
from src.core.agent import RunContext
from src.core.agent.discovery import ReActDiscoveryAgent
from src.core.agent.drivers import PlaywrightCLIDriver
from src.core.agent.llm import RecipeSummaryRequest, ToolSelectionRequest
from src.core.agent.models import LocatorSpec
from src.core.agent.models import SecurityPolicy
from src.core.agent.replay import ReplayRunner
from src.core.agent.security import validate_locator, validate_navigation_target
from src.core.agent.tools import ToolCall
from src.domains.agent_recipe.repository import AgentRecipeRepository
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
    run_id: str,
    goal: str,
    entrypoint_url: str,
    namespace_hint: str | None = None,
    key_hint: str | None = None,
    max_steps: int | None = None,
) -> dict[str, Any]:
    settings = get_settings().shop_dashboard
    try:
        result = _run_discovery(
            run_id=run_id,
            goal=goal,
            entrypoint_url=entrypoint_url,
            namespace_hint=namespace_hint,
            key_hint=key_hint,
            max_steps=max_steps,
            settings=settings,
        )
        if result.get("status") != "completed":
            append_discovery_event(
                run_id,
                {
                    "event_type": "run_finished",
                    "status": result.get("status") or "failed",
                    "message": result.get("error_message") or "discovery failed",
                },
            )
            return result
        recipe = result.get("recipe")
        if not isinstance(recipe, dict):
            raise RuntimeError("discovery recipe missing")
        replay = _replay_recipe(
            run_id=run_id,
            recipe=recipe,
            settings=settings,
        )
        if not replay.success:
            raise RuntimeError(replay.reason or "discovery replay failed")
        written = _write_agent_recipe(recipe)
        append_discovery_event(
            run_id,
            {
                "event_type": "run_finished",
                "status": "completed",
                "message": "discovery recipe persisted",
            },
        )
        return {
            "status": "completed",
            "run_id": run_id,
            "recipe_id": written.get("id"),
            "recipe_version": written.get("version"),
        }
    except Exception as exc:
        message = str(exc) or type(exc).__name__
        append_discovery_event(
            run_id,
            {
                "event_type": "run_failed",
                "status": "failed",
                "message": message,
            },
        )
        append_discovery_event(
            run_id,
            {
                "event_type": "run_finished",
                "status": "failed",
                "message": message,
            },
        )
        return {"status": "failed", "run_id": run_id, "message": message}


def _run_discovery(
    *,
    run_id: str,
    goal: str,
    entrypoint_url: str,
    namespace_hint: str | None,
    key_hint: str | None,
    max_steps: int | None,
    settings: Any,
) -> dict[str, Any]:
    driver = PlaywrightCLIDriver(
        session_id=run_id,
        artifact_dir=settings.agent_artifact_dir,
    )
    llm_client = _ConfiguredDiscoveryLLMClient(settings=settings)
    security_policy = SecurityPolicy(
        allowed_origins=list(settings.agent_allowed_origins)
    )
    agent = ReActDiscoveryAgent(
        driver=driver,
        llm_client=llm_client,
        security=_DiscoverySecurity(),
        event_sink=lambda event: _append_agent_event(run_id, event),
        max_steps=max_steps or settings.agent_max_steps,
    )
    driver.open(None, headed=bool(settings.agent_browser_headed))
    try:
        result = agent.run(
            goal=goal,
            entrypoint_url=entrypoint_url,
            run_id=run_id,
            namespace_hint=namespace_hint,
            key_hint=key_hint,
            security_policy=security_policy,
            max_steps=max_steps,
        )
        return result.model_dump(mode="json")
    finally:
        llm_client.close()
        driver.close()


def _replay_recipe(
    *,
    run_id: str,
    recipe: dict[str, Any],
    settings: Any,
):
    return ReplayRunner(
        _DiscoveryReplayCrawler(run_id=run_id, settings=settings)
    ).replay(
        recipe,
        context={"session_id": f"{run_id}-replay"},
    )


def _write_agent_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    parsed = Recipe.model_validate(_normalize_recipe_payload(recipe))
    payload = parsed.model_dump(mode="json", exclude={"metadata"})

    async def _write() -> dict[str, Any]:
        session_factory = session_module.async_session_factory
        if session_factory is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")
        async with session_factory() as db_session:
            repository = AgentRecipeRepository(db_session)
            current_recipe = await repository.get_active_for_update(
                parsed.namespace,
                parsed.key,
            )
            if current_recipe is None:
                written = await repository.create(payload)
            else:
                written = await repository.create_next_version(
                    current_recipe=current_recipe,
                    data={
                        "entrypoint": payload["entrypoint"],
                        "steps": payload["steps"],
                        "observations": payload["observations"],
                        "assertions": payload["assertions"],
                        "recovery_policy": payload["recovery_policy"],
                        "security_policy": payload["security_policy"],
                    },
                )
            await db_session.commit()
            return {"id": written.id, "version": written.version}

    return session_module.run_coro(_write())


class _DiscoveryReplayCrawler:
    def __init__(self, *, run_id: str, settings: Any) -> None:
        self._run_id = run_id
        self._settings = settings

    def run(
        self,
        recipe: dict[str, Any],
        *,
        input_data: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> Any:
        _ = input_data
        parsed = Recipe.model_validate(_normalize_recipe_payload(recipe))
        run_context = RunContext(
            session_id=str(
                (context or {}).get("session_id") or f"{self._run_id}-replay"
            ),
            headed=bool(self._settings.agent_browser_headed),
        )
        driver = PlaywrightCLIDriver(
            session_id=run_context.session_id,
            artifact_dir=self._settings.agent_artifact_dir,
        )
        return AgentCrawler(driver).run(parsed, run_context)


class _DiscoverySecurity:
    DEFAULT_POLICY: dict[str, Any] = {}

    def validate_locator(self, locator: Any) -> None:
        parsed = (
            locator
            if isinstance(locator, LocatorSpec)
            else LocatorSpec.model_validate(locator)
        )
        validate_locator(parsed)

    def validate_navigation_target(self, url: str, security_policy: Any | None) -> None:
        if security_policy is None:
            return
        validate_navigation_target(url, security_policy)


class _ConfiguredDiscoveryLLMClient:
    def __init__(self, *, settings: Any, client: httpx.Client | None = None) -> None:
        self._settings = settings
        api_key = str(getattr(settings, "llm_api_key", "") or "").strip()
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = client or httpx.Client(headers=headers)
        self._owns_client = client is None

    def complete_tool_call(self, request: ToolSelectionRequest) -> ToolCall:
        payload = self._post(
            [
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "choose_next_browser_tool",
                            "request": request.model_dump(mode="json"),
                            "response_schema": {
                                "name": "tool name",
                                "arguments": "tool arguments object",
                            },
                            "response_format_instruction": "Return a JSON object only.",
                        },
                        ensure_ascii=False,
                    ),
                }
            ]
        )
        return ToolCall.model_validate(_extract_tool_call(payload))

    def summarize_recipe(self, request: RecipeSummaryRequest) -> dict[str, Any]:
        payload = self._post(
            [
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "generate_browser_agent_recipe",
                            "request": request.model_dump(mode="json"),
                            "response_format_instruction": "Return a JSON object only.",
                        },
                        ensure_ascii=False,
                    ),
                }
            ]
        )
        return payload

    def _post(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        endpoint = str(self._settings.llm_endpoint or "").strip()
        model = str(self._settings.llm_model or "").strip()
        if not endpoint or not model:
            raise RuntimeError("agent_discovery_llm_not_configured")
        provider = str(self._settings.llm_provider or "claude").strip().lower()
        timeout = int(self._settings.llm_timeout_seconds or 120)
        body: dict[str, Any]
        if provider == "openai":
            body = {
                "model": model,
                "response_format": {"type": "json_object"},
                "messages": messages,
            }
        else:
            body = {
                "model": model,
                "max_tokens": 4096,
                "messages": messages,
            }
        response = self._client.post(endpoint, json=body, timeout=timeout)
        response.raise_for_status()
        parsed = _parse_llm_response(response.json())
        if not parsed:
            raise RuntimeError("agent_discovery_llm_empty_response")
        return parsed

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def _parse_llm_response(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    if "name" in data or "entrypoint" in data:
        return data
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            parsed = _parse_json_text(message.get("content"))
            if parsed:
                return parsed
    content = data.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            parsed = _parse_json_text(item.get("text"))
            if parsed:
                return parsed
    return {}


def _parse_json_text(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_tool_call(payload: dict[str, Any]) -> dict[str, Any]:
    if "name" in payload:
        return payload
    name = payload.get("tool_name") or payload.get("tool")
    arguments = payload.get("arguments") or payload.get("args") or {}
    return {"name": name, "arguments": arguments}


def _append_agent_event(run_id: str, event: Any) -> dict[str, Any] | None:
    event_type = getattr(event, "event_type", None)
    if event_type == "run_finished":
        return None
    return append_discovery_event(run_id, event)


def _normalize_recipe_payload(recipe: dict[str, Any]) -> dict[str, Any]:
    payload = dict(recipe)
    payload.pop("id", None)
    payload.pop("recipe_id", None)
    payload.pop("status", None)
    entrypoint = payload.get("entrypoint")
    if (
        isinstance(entrypoint, dict)
        and "url_template" in entrypoint
        and "url" not in entrypoint
    ):
        normalized_entrypoint = dict(entrypoint)
        normalized_entrypoint["url"] = normalized_entrypoint.pop("url_template")
        payload["entrypoint"] = normalized_entrypoint
    return payload
