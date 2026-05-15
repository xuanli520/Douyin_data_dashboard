from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DiscoveryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    event_type: str
    sequence: int | None = None
    current_url: str | None = None
    page_title: str | None = None
    screenshot_artifact_id: str | None = None
    status: str | None = None
    message: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] | None = None
    tool_result: Any = None
    snapshot_text: str | None = None
    thought: str | None = None
    llm_prompt: dict[str, Any] | None = None
    llm_raw_response: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
