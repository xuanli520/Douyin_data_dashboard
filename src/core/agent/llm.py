from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from src.core.agent.tools import ToolCall


class ToolSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    entrypoint_url: str
    current_observation: dict[str, Any] = Field(default_factory=dict)
    tool_history: list[dict[str, Any]] = Field(default_factory=list)
    available_tools: list[dict[str, Any]] = Field(default_factory=list)
    step_index: int = 0
    max_steps: int = 30


class RecipeSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    entrypoint_url: str
    trajectory: dict[str, Any]
    namespace_hint: str | None = None
    key_hint: str | None = None


@runtime_checkable
class DiscoveryLLMClient(Protocol):
    def complete_tool_call(self, request: ToolSelectionRequest) -> ToolCall:
        ...

    def summarize_recipe(self, request: RecipeSummaryRequest) -> dict[str, Any]:
        ...
