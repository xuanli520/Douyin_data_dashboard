from __future__ import annotations

from typing import Any, Callable, Mapping, get_args
from urllib.parse import urlparse

from src.core.agent.llm import DiscoveryLLMClient, RecipeSummaryRequest
from src.core.agent.models import ActionName
from src.core.agent.models import SecurityPolicy
from src.core.agent.tools import ToolRegistry


class RecipeGenerationError(ValueError):
    pass


_RECIPE_ACTIONS = set(get_args(ActionName))


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
        recipe = self.normalize_recipe(raw_recipe, request=request)
        try:
            return self.validate_recipe(recipe)
        except RecipeGenerationError as exc:
            repaired = self._repair_recipe(
                request=request,
                recipe=recipe,
                error_message=str(exc),
            )
            if repaired is None:
                raise
            return self.validate_recipe(repaired)

    def normalize_recipe(
        self,
        value: Mapping[str, Any] | dict[str, Any],
        *,
        request: RecipeSummaryRequest,
    ) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise RecipeGenerationError("recipe must be an object")
        recipe = _unwrap_recipe(value)
        namespace = str(request.namespace_hint or recipe.get("namespace") or "").strip()
        key = str(request.key_hint or recipe.get("key") or "").strip()
        if namespace:
            recipe["namespace"] = namespace
        if key:
            recipe["key"] = key
        recipe["entrypoint"] = _normalize_entrypoint(
            recipe.get("entrypoint"),
            request.entrypoint_url,
        )
        recipe["steps"] = _normalize_steps(recipe.get("steps"), request.entrypoint_url)
        recipe["observations"] = _normalize_observations(recipe.get("observations"))
        recipe["assertions"] = _normalize_assertions(recipe.get("assertions"))
        recipe["security_policy"] = _normalize_security_policy(
            recipe.get("security_policy"),
            request.entrypoint_url,
        )
        recipe.setdefault(
            "recovery_policy",
            {"enabled": True, "minimum_confidence": 0.7, "max_attempts": 1},
        )
        return recipe

    def validate_recipe(
        self, value: Mapping[str, Any] | dict[str, Any]
    ) -> dict[str, Any]:
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
        entrypoint_url = str(
            entrypoint.get("url_template") or entrypoint.get("url") or ""
        ).strip()
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
            if action not in _RECIPE_ACTIONS:
                raise RecipeGenerationError(f"unsupported recipe action: {action}")
            target = step.get("target")
            if target is not None:
                self._validate_locator_payload(target)
        observation_ids = self._validate_observations(recipe.get("observations"))
        self._validate_assertions(recipe.get("assertions"), observation_ids)
        self._validate_security_policy(security_policy)
        return recipe

    def _validate_entrypoint(self, url: str, security_policy: Any | None) -> None:
        if self._validate_navigation_target is not None:
            self._validate_navigation_target(
                url,
                _security_policy_model(security_policy),
            )
            return
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RecipeGenerationError(
                "entrypoint url must be absolute http or https url"
            )
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
            pairs = [
                (item.get("id"), item) for item in value if isinstance(item, Mapping)
            ]
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
        for assertion in value:
            if not isinstance(assertion, Mapping):
                raise RecipeGenerationError("assertion must be an object")
            source = str(assertion.get("source") or "").strip()
            if not source:
                raise RecipeGenerationError("assertion source is required")
            if source not in allowed_sources:
                raise RecipeGenerationError(
                    f"assertion source does not exist: {source}"
                )

    def _validate_security_policy(self, value: Any) -> None:
        if not self._system_security_policy:
            return
        candidate = dict(value or {}) if isinstance(value, Mapping) else {}
        baseline_allowed_tools = set(
            self._system_security_policy.get("allowed_tools") or self._registry.names()
        )
        candidate_allowed_tools = set(
            candidate.get("allowed_tools") or baseline_allowed_tools
        )
        if not candidate_allowed_tools.issubset(baseline_allowed_tools):
            raise RecipeGenerationError("security policy cannot expand allowed tools")
        baseline_allowed_origins = set(
            self._system_security_policy.get("allowed_origins") or []
        )
        candidate_allowed_origins = set(
            candidate.get("allowed_origins") or baseline_allowed_origins
        )
        if baseline_allowed_origins and not candidate_allowed_origins.issubset(
            baseline_allowed_origins
        ):
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

    def _repair_recipe(
        self,
        *,
        request: RecipeSummaryRequest,
        recipe: dict[str, Any],
        error_message: str,
    ) -> dict[str, Any] | None:
        repair = getattr(self._llm_client, "repair_recipe", None)
        if not callable(repair):
            return None
        repaired = repair(
            request=request,
            invalid_recipe=recipe,
            error_message=error_message,
        )
        if not isinstance(repaired, Mapping):
            return None
        return self.normalize_recipe(repaired, request=request)


def _unwrap_recipe(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(value)
    for key in ("recipe", "data"):
        nested = payload.get(key)
        if isinstance(nested, Mapping):
            return dict(nested)
    return payload


def _normalize_entrypoint(value: Any, entrypoint_url: str) -> dict[str, Any]:
    entrypoint = dict(value) if isinstance(value, Mapping) else {}
    if not str(entrypoint.get("url") or entrypoint.get("url_template") or "").strip():
        entrypoint["url"] = entrypoint_url
    return entrypoint


def _normalize_steps(value: Any, entrypoint_url: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        return [{"id": "open_entrypoint", "action": "goto", "value": entrypoint_url}]
    steps: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, Mapping):
            steps.append(item)
            continue
        step = dict(item)
        if str(step.get("action") or "").strip() == "done":
            continue
        step.setdefault("id", f"step-{index}")
        arguments = step.pop("arguments", None)
        if isinstance(arguments, Mapping):
            if "target" not in step and "locator" in arguments:
                step["target"] = arguments["locator"]
            if "value" not in step and "value" in arguments:
                step["value"] = arguments["value"]
            if "value" not in step and "url" in arguments:
                step["value"] = arguments["url"]
            if "timeout_seconds" not in step and "timeout_seconds" in arguments:
                step["timeout_seconds"] = arguments["timeout_seconds"]
        steps.append(step)
    return steps


def _normalize_observations(value: Any) -> dict[str, dict[str, Any]]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        pairs = value.items()
    elif isinstance(value, list):
        pairs = [(item.get("id"), item) for item in value if isinstance(item, Mapping)]
    else:
        return value
    observations: dict[str, dict[str, Any]] = {}
    for key, item in pairs:
        if not isinstance(item, Mapping):
            continue
        observation = dict(item)
        observation_id = str(observation.get("id") or key or "").strip()
        if not observation_id:
            continue
        observation["id"] = observation_id
        observations[observation_id] = observation
    return observations


def _normalize_assertions(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        return value
    assertions: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        assertion = dict(item)
        if "kind" not in assertion and "type" in assertion:
            assertion["kind"] = assertion.pop("type")
        if "source" not in assertion and "observation" in assertion:
            assertion["source"] = assertion.pop("observation")
        assertions.append(assertion)
    return assertions


def _normalize_security_policy(value: Any, entrypoint_url: str) -> dict[str, Any]:
    policy = dict(value) if isinstance(value, Mapping) else {}
    origins = policy.get("allowed_origins")
    if not isinstance(origins, list) or not origins:
        origin = _origin(entrypoint_url)
        if origin:
            policy["allowed_origins"] = [origin]
    return policy


def _security_policy_model(value: Any | None) -> SecurityPolicy:
    if isinstance(value, SecurityPolicy):
        return value
    if isinstance(value, Mapping):
        return SecurityPolicy.model_validate(value)
    return SecurityPolicy()


def _origin(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"
