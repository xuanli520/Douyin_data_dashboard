from src.core.agent.failures import FailureClassifier, FailureType


def test_marks_locator_failure_recoverable_for_observation_locator():
    result = FailureClassifier().classify(
        {
            "type": "locator_not_found",
            "failed_targets": ["/observations/total/locator"],
            "reason": "missing locator",
        }
    )

    assert result.failure_type is FailureType.LOCATOR_NOT_FOUND
    assert result.recoverable is True
    assert result.failed_targets == ["/observations/total/locator"]
    assert result.reason == "missing locator"


def test_normalizes_observation_id_into_locator_target():
    result = FailureClassifier().classify(
        {
            "type": "parse_failed",
            "observation_id": "price",
            "reason": "empty text",
        }
    )

    assert result.failure_type is FailureType.PARSE_FAILED
    assert result.recoverable is True
    assert result.failed_targets == ["/observations/price/locator"]


def test_marks_auth_failure_non_recoverable():
    result = FailureClassifier().classify(
        {
            "type": "auth_required",
            "failed_targets": ["/observations/total/locator"],
        }
    )

    assert result.failure_type is FailureType.AUTH_REQUIRED
    assert result.recoverable is False
