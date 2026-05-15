from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class ReplayCrawler(Protocol):
    def run(
        self,
        recipe: dict[str, Any],
        *,
        input_data: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> Any: ...


@dataclass(slots=True)
class ReplayOutcome:
    success: bool
    failed_targets: list[str] = field(default_factory=list)
    recovered_targets: list[str] = field(default_factory=list)
    reason: str = ""
    raw: Any = None


class ReplayRunner:
    def __init__(self, crawler: ReplayCrawler | Any) -> None:
        self._crawler = crawler

    def replay(
        self,
        recipe: dict[str, Any],
        *,
        input_data: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        failed_targets: list[str] | None = None,
    ) -> ReplayOutcome:
        expected_targets = list(failed_targets or [])
        try:
            if hasattr(self._crawler, "run"):
                payload = self._crawler.run(
                    recipe,
                    input_data=input_data,
                    context=context,
                )
            else:
                payload = self._crawler(
                    recipe,
                    input_data=input_data,
                    context=context,
                )
        except Exception as exc:
            return ReplayOutcome(
                success=False,
                failed_targets=expected_targets,
                reason=str(exc),
                raw={"error": str(exc)},
            )
        return self._to_outcome(payload, expected_targets)

    def _to_outcome(self, payload: Any, expected_targets: list[str]) -> ReplayOutcome:
        if isinstance(payload, ReplayOutcome):
            outcome = payload
        elif isinstance(payload, dict):
            success = bool(payload.get("success", not payload.get("failed_targets")))
            outcome = ReplayOutcome(
                success=success,
                failed_targets=list(payload.get("failed_targets") or []),
                recovered_targets=list(payload.get("recovered_targets") or []),
                reason=str(payload.get("reason", "")),
                raw=payload,
            )
        elif hasattr(payload, "ok") and hasattr(payload, "status"):
            success = bool(getattr(payload, "ok"))
            failure = getattr(payload, "failure", None)
            reason = ""
            if failure is not None:
                reason = str(getattr(failure, "message", "") or getattr(failure, "kind", ""))
            outcome = ReplayOutcome(
                success=success,
                failed_targets=[] if success else expected_targets,
                recovered_targets=list(expected_targets) if success else [],
                reason=reason,
                raw=payload,
            )
        else:
            outcome = ReplayOutcome(success=bool(payload), raw=payload)
        if outcome.success and expected_targets:
            recovered = set(outcome.recovered_targets)
            missing_targets = [target for target in expected_targets if target not in recovered]
            if missing_targets:
                return ReplayOutcome(
                    success=False,
                    failed_targets=missing_targets,
                    recovered_targets=outcome.recovered_targets,
                    reason="replay_missing_targets",
                    raw=outcome.raw,
                )
        return outcome
