from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PageObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_url: str | None = None
    page_title: str | None = None
    screenshot_artifact_id: str | None = None
    snapshot_text: str | None = None
    tool_results: list[dict[str, Any]] = Field(default_factory=list)


class TrajectoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_index: int
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    observation: PageObservation | None = None
    status: Literal["ok", "failed"] = "ok"
    error_message: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class DiscoveryTrajectory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    goal: str
    entrypoint_url: str
    status: Literal["running", "completed", "failed"] = "running"
    entries: list[TrajectoryEntry] = Field(default_factory=list)
    recipe: dict[str, Any] | None = None
    error_message: str | None = None
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None

    def append_entry(
        self,
        *,
        step_index: int,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
        observation: PageObservation | None,
        status: Literal["ok", "failed"] = "ok",
        error_message: str | None = None,
    ) -> TrajectoryEntry:
        entry = TrajectoryEntry(
            step_index=step_index,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            observation=observation,
            status=status,
            error_message=error_message,
        )
        self.entries.append(entry)
        return entry

    def latest_observation(self) -> PageObservation | None:
        for entry in reversed(self.entries):
            if entry.observation is not None:
                return entry.observation
        return None

    def tool_history(self) -> list[dict[str, Any]]:
        return [entry.model_dump(mode="json") for entry in self.entries]

    def mark_completed(self, recipe: dict[str, Any]) -> None:
        self.status = "completed"
        self.recipe = recipe
        self.completed_at = _utcnow()

    def mark_failed(self, error_message: str) -> None:
        self.status = "failed"
        self.error_message = error_message
        self.completed_at = _utcnow()
