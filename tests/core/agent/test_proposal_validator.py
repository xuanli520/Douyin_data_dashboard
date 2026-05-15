import pytest

from src.core.agent.failures import FailureClassification, FailureType
from src.core.agent.proposal_validator import ProposalValidationError, ProposalValidator


def _recipe() -> dict:
    return {
        "version": 3,
        "observations": {
            "total": {
                "locator": {"type": "css", "value": ".old-total"},
            }
        },
        "recovery_policy": {
            "enabled": True,
            "confidence_threshold": 0.7,
        },
    }


def _failure() -> FailureClassification:
    return FailureClassification(
        failure_type=FailureType.LOCATOR_NOT_FOUND,
        recoverable=True,
        reason="missing locator",
        failed_targets=["/observations/total/locator"],
    )


def test_validate_replaces_failed_observation_locator():
    recipe = _recipe()
    candidate = ProposalValidator().validate(
        {
            "base_version": 3,
            "confidence": 0.91,
            "reason": "replace locator",
            "patches": [
                {
                    "op": "replace",
                    "path": "/observations/total/locator",
                    "value": {"type": "css", "value": ".new-total"},
                    "confidence": 0.91,
                }
            ],
        },
        recipe,
        _failure(),
    )

    assert candidate["observations"]["total"]["locator"]["value"] == ".new-total"
    assert recipe["observations"]["total"]["locator"]["value"] == ".old-total"


def test_validate_rejects_patch_outside_failed_targets():
    with pytest.raises(ProposalValidationError, match="patch_target_not_failed"):
        ProposalValidator().validate(
            {
                "base_version": 3,
                "confidence": 0.91,
                "reason": "replace locator",
                "patches": [
                    {
                        "op": "replace",
                        "path": "/observations/other/locator",
                        "value": {"type": "css", "value": ".new-total"},
                    }
                ],
            },
            _recipe(),
            _failure(),
        )


def test_validate_rejects_non_replace_operation():
    with pytest.raises(ProposalValidationError, match="patch_operation_not_allowed"):
        ProposalValidator().validate(
            {
                "base_version": 3,
                "confidence": 0.91,
                "reason": "replace locator",
                "patches": [
                    {
                        "op": "append",
                        "path": "/observations/total/locator",
                        "value": {"type": "css", "value": ".new-total"},
                    }
                ],
            },
            _recipe(),
            _failure(),
        )
