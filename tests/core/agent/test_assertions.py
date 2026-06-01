import pytest

from src.core.agent.assertions import evaluate_assertions
from src.core.agent.exceptions import AssertionFailedError
from src.core.agent.models import AssertionSpec


def test_evaluate_assertions_raises_for_error():
    with pytest.raises(AssertionFailedError):
        evaluate_assertions(
            assertions=[AssertionSpec(id="required", kind="not_empty", source="value")],
            values={"value": ""},
        )


def test_evaluate_assertions_returns_warnings():
    warnings = evaluate_assertions(
        assertions=[
            AssertionSpec(
                id="warn",
                kind="contains",
                source="value",
                expected="missing",
                severity="warning",
            )
        ],
        values={"value": "present"},
    )

    assert [warning.id for warning in warnings] == ["warn"]
