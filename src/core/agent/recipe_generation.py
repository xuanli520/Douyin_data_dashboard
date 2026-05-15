from __future__ import annotations

from typing import Any, Callable, Mapping
from urllib.parse import urlparse

from src.core.agent.llm import DiscoveryLLMClient, RecipeSummaryRequest
from src.core.agent.tools import ToolRegistry


class RecipeGenerationError(ValueError):
    pass


class RecipeGenerator:
    def __init__(
        self,
        llm_client: DiscoveryLLMClient,
        *,
        registry: ToolRegistry | None = None,
        validate_locator: Callable[[Any], None] | None = None,
        validate_navigation_target: Callable[[str, Any | None], None] | None = None,
        system_security_policy: Mapping[str, Any] | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._registry = registry or ToolRegistry()
        self._validate_locator = validate_locator
        self._validate_navigation_target = validate_navigation_target
        self._system_security_policy = dict(system_security_policy or {})

    def generate(self, request: RecipeSummaryRequest) -> dict[str, Any]:
        raw_recipe = self._llm_client.summarize_recipe(request)
        return self.validate_recipe(raw_recipe)

    def validate_recipe(self, value: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise RecipeGenerationError("recipe must be an object")
        recipe = dict(value)
        namespace = str(recipe.get("namespace") or "").strip()
        key = str(recipe.get("key") or "").strip()
        if not namespace:
            raise RecipeGenerationError("namespace is required")
        if not key:
            raise RecipeGenerationError("key is required")
        entrypoint = recipe.get("entrypoint")
        if not isinstance(entrypoint, Mapping):
            raise RecipeGenerationError("entrypoint is required")
        entrypoint_url = str(entrypoint.get("url_template") or entrypoint.get("url") or "").strip()
        if not entrypoint_url:
            raise RecipeGenerationError("entrypoint url is required")
        security_policy = recipe.get("security_policy")
        self._validate_entrypoint(entrypoint_url, security_policy)
        steps = recipe.get("steps")
        if not isinstance(steps, list) or not steps:
            raise RecipeGenerationError("steps must be a non-empty list")
        for step in steps:
            if not isinstance(step, Mapping):
                raise RecipeGenerationError("step must be an object")
            action = str(step.get("action") or "").strip()
            if not action:
                raise RecipeGenerationError("step action is required")
            try:
                self._registry.get(action)
            except ValueError as exc:
                raise RecipeGenerationError(str(exc)) from exc
            target = step.get("target")
            if target is not None:
                self._validate_locator_payload(target)
        observation_ids = self._validate_observations(recipe.get("observations"))
        self._validate_assertions(recipe.get("assertions"), observation_ids)
        self._validate_security_policy(security_policy)
        return recipe

    def _validate_entrypoint(self, url: str, security_policy: Any | None) -> None:
        if self._validate_navigation_target is not None:
            self._validate_navigation_target(url, security_policy)
            return
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RecipeGenerationError("entrypoint url must be absolute http or https url")
        allowed_origins = self._extract_allowed_origins(security_policy)
        if allowed_origins:
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if origin not in allowed_origins:
                raise RecipeGenerationError("entrypoint url is not allowlisted")

    def _extract_allowed_origins(self, security_policy: Any | None) -> set[str]:
        if isinstance(security_policy, Mapping):
            values = security_policy.get("allowed_origins") or []
            return {str(value).strip() for value in values if str(value).strip()}
        if security_policy is None:
            return set()
        values = getattr(security_policy, "allowed_origins", []) or []
        return {str(value).strip() for value in values if str(value).strip()}

    def _validate_observations(self, value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, Mapping):
            pairs = list(value.items())
        elif isinstance(value, list):
            pairs = [(item.get("id"), item) for item in value if isinstance(item, Mapping)]
            if len(pairs) != len(value):
                raise RecipeGenerationError("observation must be an object")
        else:
            raise RecipeGenerationError("observations must be an object or list")
        observation_ids: list[str] = []
        for key, observation in pairs:
            if not isinstance(observation, Mapping):
                raise RecipeGenerationError("observation must be an object")
            observation_id = str(observation.get("id") or key or "").strip()
            if not observation_id:
                raise RecipeGenerationError("observation id is required")
            observation_ids.append(observation_id)
            locator = observation.get("locator")
            if locator is not None:
                self._validate_locator_payload(locator)
        if len(observation_ids) != len(set(observation_ids)):
            raise RecipeGenerationError("observation ids must be unique")
        return set(observation_ids)

    def _validate_assertions(self, value: Any, observation_ids: set[str]) -> None:
        if value is None:
            return
        if not isinstance(value, list):
            raise RecipeGenerationError("assertions must be a list")
        allowed_sources = set(observation_ids)
        allowed_sources.update({"current_url", "page_title"})
        for assertion in value:
            if not isinstance(assertion, Mapping):
                raise RecipeGenerationError("assertion must be an object")
            source = str(assertion.get("source") or "").strip()
            if not source:
                raise RecipeGenerationError("assertion source is required")
            if source not in allowed_sources:
                raise RecipeGenerationError(f"assertion source does not exist: {source}")

    def _validate_security_policy(self, value: Any) -> None:
        if not self._system_security_policy:
            return
        candidate = dict(value or {}) if isinstance(value, Mapping) else {}
        baseline_allowed_tools = set(
            self._system_security_policy.get("allowed_tools") or self._registry.names()
        )
        candidate_allowed_tools = set(candidate.get("allowed_tools") or baseline_allowed_tools)
        if not candidate_allowed_tools.issubset(baseline_allowed_tools):
            raise RecipeGenerationError("security policy cannot expand allowed tools")
        baseline_allowed_origins = set(self._system_security_policy.get("allowed_origins") or [])
        candidate_allowed_origins = set(candidate.get("allowed_origins") or baseline_allowed_origins)
        if baseline_allowed_origins and not candidate_allowed_origins.issubset(baseline_allowed_origins):
            raise RecipeGenerationError("security policy cannot expand allowed origins")

    def _validate_locator_payload(self, locator: Any) -> None:
        if self._validate_locator is not None:
            self._validate_locator(locator)
            return
        value = locator
        if isinstance(locator, Mapping):
            value = locator.get("value")
        locator_value = str(value or "").strip().lower()
        if not locator_value:
            raise RecipeGenerationError("locator value is required")
        blocked_tokens = ("javascript:", "<script", "eval(", "onclick=", "onerror=")
        if any(token in locator_value for token in blocked_tokens):
            raise RecipeGenerationError("locator contains blocked pattern")
