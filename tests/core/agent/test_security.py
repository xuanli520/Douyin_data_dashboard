import pytest

from src.core.agent.exceptions import SecurityPolicyError
from src.core.agent.models import LocatorSpec
from src.core.agent.models import SecurityPolicy
from src.core.agent.security import validate_locator
from src.core.agent.security import validate_navigation_target
from src.core.agent.security import validate_page_risk
from src.core.agent.security import validate_tool_name


def test_validate_tool_name_rejects_blocked_tool():
    with pytest.raises(SecurityPolicyError):
        validate_tool_name("evaluate")


def test_validate_navigation_target_rejects_unknown_origin():
    with pytest.raises(SecurityPolicyError):
        validate_navigation_target(
            "https://blocked.test/path",
            SecurityPolicy(allowed_origins=["https://allowed.test"]),
        )


def test_validate_locator_rejects_blocked_pattern():
    with pytest.raises(SecurityPolicyError):
        validate_locator(LocatorSpec(kind="css", value="button[data-action='delete']"))


def test_validate_page_risk_rejects_blocked_keyword():
    with pytest.raises(SecurityPolicyError):
        validate_page_risk("https://allowed.test", "Checkout", "safe")
