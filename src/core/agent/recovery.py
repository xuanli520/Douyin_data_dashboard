from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from src.core.agent.failures import FailureClassification, FailureClassifier
from src.core.agent.proposal_validator import ProposalValidationError, ProposalValidator
from src.core.agent.proposals import (
    RecoveryPolicy,
    RecoveryProposal,
    RecoveryRequest,
)
from src.core.agent.recovery_prompts import build_recovery_messages
from src.core.agent.replay import ReplayOutcome, ReplayRunner


class RecoveryModel(Protocol):
    def propose_recovery(
        self,
        request: RecoveryRequest,
        messages: list[dict[str, str]],
    ) -> RecoveryProposal | dict[str, Any]: ...


@dataclass(slots=True)
class RecoveryResult:
    status: str
    reason: str
    classification: FailureClassification
    request: RecoveryRequest | None = None
    proposal: RecoveryProposal | None = None
    candidate_recipe: dict[str, Any] | None = None
    replay: ReplayOutcome | None = None

    @property
    def success(self) -> bool:
        return self.status == "recovered"


class RecoveryService:
    def __init__(
        self,
        model: RecoveryModel,
        crawler: Any,
        *,
        classifier: FailureClassifier | None = None,
        validator: ProposalValidator | None = None,
    ) -> None:
        self._model = model
        self._classifier = classifier or FailureClassifier()
        self._validator = validator or ProposalValidator()
        self._replay_runner = ReplayRunner(crawler)

    def recover(
        self,
        recipe: dict[str, Any],
        failure: dict[str, Any] | None,
        *,
        input_data: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        artifacts: dict[str, Any] | None = None,
        policy: RecoveryPolicy | dict[str, Any] | None = None,
        attempt: int = 1,
    ) -> RecoveryResult:
        parsed_policy = RecoveryPolicy.from_value(policy or recipe.get("recovery_policy"))
        classification = self._classifier.classify(failure)
        if not parsed_policy.enabled:
            return RecoveryResult(
                status="skipped",
                reason="recovery_disabled",
                classification=classification,
            )
        if attempt > parsed_policy.max_attempts:
            return RecoveryResult(
                status="skipped",
                reason="recovery_attempt_limit",
                classification=classification,
            )
        if not classification.recoverable:
            return RecoveryResult(
                status="skipped",
                reason=classification.failure_type.value,
                classification=classification,
            )
        request = self._build_request(recipe, classification, parsed_policy, artifacts)
        proposal = RecoveryProposal.from_value(
            self._model.propose_recovery(request, build_recovery_messages(request))
        )
        try:
            candidate_recipe = self._validator.validate(
                proposal,
                recipe,
                classification,
                parsed_policy,
            )
        except ProposalValidationError as exc:
            return RecoveryResult(
                status="proposal_invalid",
                reason=str(exc),
                classification=classification,
                request=request,
                proposal=proposal,
            )
        replay = self._replay_runner.replay(
            candidate_recipe,
            input_data=input_data,
            context=context,
            failed_targets=classification.failed_targets,
        )
        if not replay.success:
            return RecoveryResult(
                status="replay_failed",
                reason=replay.reason or "replay_failed",
                classification=classification,
                request=request,
                proposal=proposal,
                candidate_recipe=candidate_recipe,
                replay=replay,
            )
        return RecoveryResult(
            status="recovered",
            reason="recovered",
            classification=classification,
            request=request,
            proposal=proposal,
            candidate_recipe=candidate_recipe,
            replay=replay,
        )

    def _build_request(
        self,
        recipe: dict[str, Any],
        classification: FailureClassification,
        policy: RecoveryPolicy,
        artifacts: dict[str, Any] | None,
    ) -> RecoveryRequest:
        artifact_data = dict(artifacts or {})
        observations = recipe.get("observations")
        observation_specs = dict(observations) if isinstance(observations, dict) else {}
        security_policy = recipe.get("security_policy")
        recipe_excerpt = {
            "entrypoint": recipe.get("entrypoint"),
            "observations": observation_specs,
        }
        return RecoveryRequest(
            recipe_id=recipe.get("id") or recipe.get("recipe_id"),
            recipe_version=(
                int(recipe["version"]) if recipe.get("version") is not None else None
            ),
            failure_type=classification.failure_type.value,
            failed_targets=list(classification.failed_targets),
            failure_reasons=list(classification.failure_reasons),
            recipe_excerpt=recipe_excerpt,
            observation_specs=observation_specs,
            security_policy=dict(security_policy) if isinstance(security_policy, dict) else {},
            recovery_policy=policy.to_dict(),
            current_url=artifact_data.get("current_url"),
            rendered_entrypoint_url=artifact_data.get("rendered_entrypoint_url"),
            snapshot_markdown=artifact_data.get("snapshot_markdown"),
            dom_excerpt=artifact_data.get("dom_excerpt"),
            screenshot_ref=artifact_data.get("screenshot_ref"),
            metadata=dict(artifact_data.get("metadata") or {}),
        )
