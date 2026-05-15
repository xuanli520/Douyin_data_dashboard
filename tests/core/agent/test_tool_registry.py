import pytest

from src.core.agent.tools import ToolRegistry


def test_tool_registry_exposes_default_tool_set():
    registry = ToolRegistry()

    assert {
        "goto",
        "click",
        "fill",
        "extract_table",
        "done",
    }.issubset(set(registry.names()))


def test_tool_registry_validates_required_arguments():
    registry = ToolRegistry()

    tool_call = registry.validate_tool_call(
        {
            "name": "click",
            "arguments": {
                "locator": {"type": "css", "value": "#submit"},
            },
        }
    )

    assert tool_call.name == "click"


def test_tool_registry_rejects_unknown_tool():
    registry = ToolRegistry()

    with pytest.raises(ValueError):
        registry.validate_tool_call({"name": "evaluate", "arguments": {}})


def test_tool_registry_rejects_missing_required_argument():
    registry = ToolRegistry()

    with pytest.raises(ValueError):
        registry.validate_tool_call(
            {
                "name": "fill",
                "arguments": {"locator": {"type": "css", "value": "#query"}},
            }
        )
