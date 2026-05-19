from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.core.agent.failures import FailureClassification
from src.core.agent.proposals import RecoveryPolicy, RecoveryProposal

_ALLOWED_LOCATOR_TYPES = {
    "css",
    "xpath",
    "text",
    "role",
    "test_id",
    "label",
    "placeholder",
}


class ProposalValidationError(ValueError):
    pass


class ProposalValidator:
    def validate(
        self,
        proposal: RecoveryProposal | dict[str, Any],
        recipe: dict[str, Any],
        failure: FailureClassification,
        policy: RecoveryPolicy | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        parsed_proposal = RecoveryProposal.from_value(proposal)
        parsed_policy = RecoveryPolicy.from_value(
            policy or recipe.get("recovery_policy")
        )
        if not parsed_policy.enabled:
            raise ProposalValidationError("recovery_disabled")
        if parsed_proposal.confidence < parsed_policy.confidence_threshold:
            raise ProposalValidationError("proposal_confidence_too_low")
        recipe_version = recipe.get("version")
        if (
            parsed_proposal.base_version is not None
            and recipe_version is not None
            and parsed_proposal.base_version != int(recipe_version)
        ):
            raise ProposalValidationError("proposal_base_version_mismatch")
        if not parsed_policy.allow_observation_locator_replace:
            raise ProposalValidationError("observation_locator_patch_disabled")
        if not parsed_proposal.patches:
            raise ProposalValidationError("proposal_has_no_patches")
        allowed_targets = {
            self.normalize_target(path) for path in failure.failed_targets
        }
        candidate = deepcopy(recipe)
        observations = candidate.get("observations")
        if not isinstance(observations, dict):
            raise ProposalValidationError("recipe_observations_invalid")
        for patch in parsed_proposal.patches:
            if patch.op != "replace":
                raise ProposalValidationError("patch_operation_not_allowed")
            if (
                patch.confidence is not None
                and patch.confidence < parsed_policy.confidence_threshold
            ):
                raise ProposalValidationError("patch_confidence_too_low")
            target = self.normalize_target(patch.path)
            if target not in allowed_targets:
                raise ProposalValidationError("patch_target_not_failed")
            observation_id = self.extract_observation_id(target)
            if observation_id not in observations:
                raise ProposalValidationError("observation_not_found")
            locator = self.validate_locator(patch.value)
            current_observation = observations.get(observation_id)
            if not isinstance(current_observation, dict):
                raise ProposalValidationError("observation_spec_invalid")
            next_observation = dict(current_observation)
            next_observation["locator"] = locator
            observations[observation_id] = next_observation
        return candidate

    def normalize_target(self, target: str) -> str:
        value = target.strip()
        if value.startswith("/observations/") and value.endswith("/locator"):
            return value
        if (
            value.startswith("/observations/")
            and "/" not in value[len("/observations/") :]
        ):
            return f"{value}/locator"
        raise ProposalValidationError("patch_path_not_allowed")

    def extract_observation_id(self, target: str) -> str:
        normalized = self.normalize_target(target)
        return normalized[len("/observations/") : -len("/locator")].strip("/")

    def validate_locator(self, locator: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(locator, dict):
            raise ProposalValidationError("locator_invalid")
        locator_type = locator.get("type")
        locator_value = locator.get("value")
        if (
            not isinstance(locator_type, str)
            or locator_type not in _ALLOWED_LOCATOR_TYPES
        ):
            raise ProposalValidationError("locator_type_not_allowed")
        if not isinstance(locator_value, str) or not locator_value.strip():
            raise ProposalValidationError("locator_value_invalid")
        lowered_value = locator_value.lower()
        if "javascript:" in lowered_value or lowered_value.startswith("js:"):
            raise ProposalValidationError("locator_value_not_allowed")
        normalized = dict(locator)
        normalized["type"] = locator_type
        normalized["value"] = locator_value.strip()
        return normalized
