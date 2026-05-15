from __future__ import annotations

from typing import Any, Callable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.core.agent.events import DiscoveryEvent
from src.core.agent.llm import DiscoveryLLMClient, RecipeSummaryRequest, ToolSelectionRequest
from src.core.agent.observation_sync import ObservationSync
from src.core.agent.recipe_generation import RecipeGenerator
from src.core.agent.tool_executor import ToolExecutor
from src.core.agent.tools import ToolRegistry
from src.core.agent.trajectory import DiscoveryTrajectory, PageObservation


class DiscoveryRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: str
    trajectory: dict[str, Any]
    recipe: dict[str, Any] | None = None
    error_message: str | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)


class ReActDiscoveryAgent:
    def __init__(
        self,
        *,
        driver: Any,
        llm_client: DiscoveryLLMClient,
        registry: ToolRegistry | None = None,
        security: Any | None = None,
        recipe_generator: RecipeGenerator | None = None,
        observation_sync: ObservationSync | None = None,
        event_sink: Callable[[DiscoveryEvent], None] | None = None,
        replay_validator: Callable[[dict[str, Any]], Any] | None = None,
        max_steps: int = 30,
    ) -> None:
        self._registry = registry or ToolRegistry()
        self._tool_executor = ToolExecutor(
            driver,
            registry=self._registry,
            security=security,
        )
        self._llm_client = llm_client
        self._recipe_generator = recipe_generator or RecipeGenerator(
            llm_client,
            registry=self._registry,
            validate_locator=getattr(security, "validate_locator", None),
            validate_navigation_target=getattr(security, "validate_navigation_target", None),
            system_security_policy=getattr(security, "DEFAULT_POLICY", None),
        )
        self._observation_sync = observation_sync or ObservationSync()
        self._event_sink = event_sink
        self._replay_validator = replay_validator
        self._max_steps = max(1, int(max_steps))

    def run(
        self,
        *,
        goal: str,
        entrypoint_url: str,
        run_id: str | None = None,
        namespace_hint: str | None = None,
        key_hint: str | None = None,
        security_policy: Any | None = None,
        max_steps: int | None = None,
    ) -> DiscoveryRunResult:
        active_run_id = run_id or uuid4().hex
        active_max_steps = max(1, int(max_steps or self._max_steps))
        self._observation_sync.reset()
        trajectory = DiscoveryTrajectory(
            run_id=active_run_id,
            goal=goal,
            entrypoint_url=entrypoint_url,
        )
        current_observation = PageObservation()
        try:
            self._emit(
                run_id=active_run_id,
                event_type="run_started",
                status="running",
                message="discovery started",
                current_url=entrypoint_url,
            )
            self._tool_executor.execute(
                {"name": "goto", "arguments": {"url": entrypoint_url}},
                security_policy=security_policy,
            )
            current_observation = PageObservation.model_validate(
                self._tool_executor.capture_observation(security_policy=security_policy)
            )
            self._emit_observation(active_run_id, current_observation, "page observed")
            for step_index in range(active_max_steps):
                tool_request = ToolSelectionRequest(
                    goal=goal,
                    entrypoint_url=entrypoint_url,
                    current_observation=current_observation.model_dump(mode="json"),
                    tool_history=trajectory.tool_history(),
                    available_tools=self._registry.prompt_payload(),
                    step_index=step_index,
                    max_steps=active_max_steps,
                )
                tool_call = self._registry.validate_tool_call(
                    self._llm_client.complete_tool_call(tool_request)
                )
                if tool_call.name == "done":
                    recipe_request = RecipeSummaryRequest(
                        goal=goal,
                        entrypoint_url=entrypoint_url,
                        trajectory=trajectory.model_dump(mode="json"),
                        namespace_hint=namespace_hint,
                        key_hint=key_hint,
                    )
                    recipe = self._recipe_generator.generate(recipe_request)
                    if self._replay_validator is not None:
                        self._replay_validator(recipe)
                    trajectory.mark_completed(recipe)
                    self._emit(
                        run_id=active_run_id,
                        event_type="recipe_generated",
                        current_url=current_observation.current_url,
                        page_title=current_observation.page_title,
                        screenshot_artifact_id=current_observation.screenshot_artifact_id,
                        status="completed",
                        message="recipe generated",
                    )
                    self._emit(
                        run_id=active_run_id,
                        event_type="run_finished",
                        current_url=current_observation.current_url,
                        page_title=current_observation.page_title,
                        screenshot_artifact_id=current_observation.screenshot_artifact_id,
                        status="completed",
                        message="discovery finished",
                    )
                    return DiscoveryRunResult(
                        run_id=active_run_id,
                        status="completed",
                        trajectory=trajectory.model_dump(mode="json"),
                        recipe=recipe,
                        events=self._observation_sync.events,
                    )
                self._emit(
                    run_id=active_run_id,
                    event_type="tool_started",
                    current_url=current_observation.current_url,
                    page_title=current_observation.page_title,
                    screenshot_artifact_id=current_observation.screenshot_artifact_id,
                    status="running",
                    message=tool_call.name,
                    tool_name=tool_call.name,
                    tool_arguments=tool_call.arguments,
                )
                tool_result = self._tool_executor.execute(
                    tool_call,
                    security_policy=security_policy,
                )
                current_observation = PageObservation.model_validate(
                    self._tool_executor.capture_observation(
                        security_policy=security_policy,
                        tool_results=[{"tool_name": tool_call.name, "result": tool_result}],
                    )
                )
                trajectory.append_entry(
                    step_index=step_index,
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments,
                    result=tool_result,
                    observation=current_observation,
                )
                self._emit(
                    run_id=active_run_id,
                    event_type="tool_finished",
                    current_url=current_observation.current_url,
                    page_title=current_observation.page_title,
                    screenshot_artifact_id=current_observation.screenshot_artifact_id,
                    status="running",
                    message=tool_call.name,
                    tool_name=tool_call.name,
                    tool_result=tool_result,
                )
                self._emit_observation(active_run_id, current_observation, "page observed")
            raise RuntimeError("max_steps_exceeded")
        except Exception as exc:
            trajectory.mark_failed(str(exc))
            self._emit(
                run_id=active_run_id,
                event_type="run_failed",
                current_url=current_observation.current_url,
                page_title=current_observation.page_title,
                screenshot_artifact_id=current_observation.screenshot_artifact_id,
                status="failed",
                message=str(exc),
            )
            self._emit(
                run_id=active_run_id,
                event_type="run_finished",
                current_url=current_observation.current_url,
                page_title=current_observation.page_title,
                screenshot_artifact_id=current_observation.screenshot_artifact_id,
                status="failed",
                message=str(exc),
            )
            return DiscoveryRunResult(
                run_id=active_run_id,
                status="failed",
                trajectory=trajectory.model_dump(mode="json"),
                error_message=str(exc),
                events=self._observation_sync.events,
            )

    def _emit_observation(
        self,
        run_id: str,
        observation: PageObservation,
        message: str,
    ) -> None:
        self._emit(
            run_id=run_id,
            event_type="page_observed",
            current_url=observation.current_url,
            page_title=observation.page_title,
            screenshot_artifact_id=observation.screenshot_artifact_id,
            status="running",
            message=message,
            snapshot_text=observation.snapshot_text,
            metadata={"tool_results": observation.tool_results},
        )

    def _emit(self, **payload: Any) -> None:
        event = DiscoveryEvent.model_validate(payload)
        if self._event_sink is not None:
            self._event_sink(event)
        self._observation_sync.publish(event)
