from __future__ import annotations

from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field


class ToolArgument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    required: bool = False


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    arguments: list[ToolArgument] = Field(default_factory=list)

    def as_prompt_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolRegistry:
    def __init__(self, definitions: Iterable[ToolDefinition] | None = None) -> None:
        active_definitions = list(definitions) if definitions is not None else self._build_default_definitions()
        self._definitions = {definition.name: definition for definition in active_definitions}

    def names(self) -> list[str]:
        return list(self._definitions)

    def definitions(self) -> list[ToolDefinition]:
        return list(self._definitions.values())

    def prompt_payload(self) -> list[dict[str, Any]]:
        return [definition.as_prompt_payload() for definition in self.definitions()]

    def get(self, name: str) -> ToolDefinition:
        definition = self._definitions.get(name)
        if definition is None:
            raise ValueError(f"unsupported tool: {name}")
        return definition

    def validate_tool_call(self, value: ToolCall | dict[str, Any]) -> ToolCall:
        tool_call = value if isinstance(value, ToolCall) else ToolCall.model_validate(value)
        definition = self.get(tool_call.name)
        argument_names = {argument.name for argument in definition.arguments}
        missing = [
            argument.name
            for argument in definition.arguments
            if argument.required and self._is_missing(tool_call.arguments.get(argument.name))
        ]
        if missing:
            raise ValueError(f"missing required arguments for {tool_call.name}: {', '.join(missing)}")
        unexpected = sorted(set(tool_call.arguments) - argument_names)
        if unexpected:
            raise ValueError(f"unexpected arguments for {tool_call.name}: {', '.join(unexpected)}")
        return tool_call

    def _is_missing(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        return False

    def _build_default_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(name="goto", arguments=[ToolArgument(name="url", required=True)]),
            ToolDefinition(name="back"),
            ToolDefinition(name="reload"),
            ToolDefinition(name="click", arguments=[ToolArgument(name="locator", required=True)]),
            ToolDefinition(
                name="fill",
                arguments=[
                    ToolArgument(name="locator", required=True),
                    ToolArgument(name="value", required=True),
                ],
            ),
            ToolDefinition(
                name="select",
                arguments=[
                    ToolArgument(name="locator", required=True),
                    ToolArgument(name="value", required=True),
                ],
            ),
            ToolDefinition(name="scroll_down", arguments=[ToolArgument(name="amount")]),
            ToolDefinition(name="scroll_up", arguments=[ToolArgument(name="amount")]),
            ToolDefinition(
                name="scroll_to_element",
                arguments=[ToolArgument(name="locator", required=True)],
            ),
            ToolDefinition(
                name="wait_visible",
                arguments=[
                    ToolArgument(name="locator", required=True),
                    ToolArgument(name="timeout_seconds"),
                ],
            ),
            ToolDefinition(
                name="wait_network_idle",
                arguments=[ToolArgument(name="timeout_seconds")],
            ),
            ToolDefinition(name="get_current_url"),
            ToolDefinition(name="get_page_title"),
            ToolDefinition(
                name="get_element_text",
                arguments=[ToolArgument(name="locator", required=True)],
            ),
            ToolDefinition(
                name="extract_table",
                arguments=[ToolArgument(name="locator", required=True)],
            ),
            ToolDefinition(
                name="extract_list",
                arguments=[ToolArgument(name="locator", required=True)],
            ),
            ToolDefinition(
                name="extract_text",
                arguments=[ToolArgument(name="locator", required=True)],
            ),
            ToolDefinition(name="done", arguments=[ToolArgument(name="message")]),
        ]
