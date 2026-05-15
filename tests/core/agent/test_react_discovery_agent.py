from src.core.agent.discovery import ReActDiscoveryAgent
from src.core.agent.tools import ToolCall


class _FakeDriver:
    def __init__(self) -> None:
        self.current_url = ""
        self.page_title = ""
        self.clicks: list[dict[str, str]] = []

    def goto(self, url):
        self.current_url = url
        self.page_title = "Landing"
        return {"url": url}

    def click(self, locator):
        self.clicks.append(locator)
        self.current_url = "https://example.com/app/results"
        self.page_title = "Results"
        return {"clicked": locator}

    def get_current_url(self):
        return self.current_url

    def get_page_title(self):
        return self.page_title

    def get_snapshot(self):
        return "snapshot text"

    def capture_screenshot(self):
        return "artifact-1"


class _FakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    def complete_tool_call(self, _request):
        self.calls += 1
        if self.calls == 1:
            return ToolCall(
                name="click",
                arguments={"locator": {"type": "css", "value": "#open"}},
            )
        return ToolCall(name="done", arguments={"message": "ready"})

    def summarize_recipe(self, _request):
        return {
            "namespace": "generic",
            "key": "auto_recipe",
            "entrypoint": {"url_template": "https://example.com/app"},
            "steps": [
                {
                    "id": "step-1",
                    "action": "click",
                    "target": {"type": "css", "value": "#open"},
                }
            ],
            "observations": {
                "result_text": {
                    "kind": "text",
                    "locator": {"type": "css", "value": ".result"},
                }
            },
            "assertions": [
                {"id": "assert-1", "source": "result_text", "kind": "not_empty"}
            ],
        }


def test_react_discovery_agent_runs_until_done():
    driver = _FakeDriver()
    llm = _FakeLLM()
    replayed = []
    agent = ReActDiscoveryAgent(
        driver=driver,
        llm_client=llm,
        replay_validator=lambda recipe: replayed.append(recipe["key"]),
        max_steps=5,
    )

    result = agent.run(
        goal="collect page result",
        entrypoint_url="https://example.com/app",
    )

    assert result.status == "completed"
    assert result.recipe["key"] == "auto_recipe"
    assert replayed == ["auto_recipe"]
    assert driver.clicks == [{"type": "css", "value": "#open"}]
    assert result.trajectory["entries"][0]["tool_name"] == "click"
    assert [event["event_type"] for event in result.events] == [
        "run_started",
        "page_observed",
        "tool_started",
        "tool_finished",
        "page_observed",
        "recipe_generated",
        "run_finished",
    ]


def test_react_discovery_agent_returns_failed_result_when_max_steps_is_hit():
    class _NeverDoneLLM(_FakeLLM):
        def complete_tool_call(self, _request):
            return ToolCall(
                name="click",
                arguments={"locator": {"type": "css", "value": "#open"}},
            )

    agent = ReActDiscoveryAgent(
        driver=_FakeDriver(),
        llm_client=_NeverDoneLLM(),
        max_steps=1,
    )

    result = agent.run(
        goal="collect page result",
        entrypoint_url="https://example.com/app",
    )

    assert result.status == "failed"
    assert result.error_message == "max_steps_exceeded"
