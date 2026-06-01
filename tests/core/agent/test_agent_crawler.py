from pathlib import Path

from src.core.agent.browser import DriverResult
from src.core.agent.crawler import AgentCrawler
from src.core.agent.exceptions import BrowserDriverError
from src.core.agent.models import Entrypoint
from src.core.agent.models import LocatorSpec
from src.core.agent.models import ObservationSpec
from src.core.agent.models import Recipe
from src.core.agent.models import RunContext
from src.core.agent.models import SecurityPolicy
from src.core.agent.models import Step


class TranscriptDriver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.closed = False

    def open(self, url: str | None = None, *, headed: bool = False) -> None:
        self.calls.append(("open", str(url)))

    def close(self) -> None:
        self.closed = True

    def goto(self, url: str) -> DriverResult:
        self.calls.append(("goto", url))
        return DriverResult()

    def back(self) -> DriverResult:
        return DriverResult()

    def reload(self) -> DriverResult:
        return DriverResult()

    def click(self, locator: LocatorSpec) -> DriverResult:
        self.calls.append(("click", locator.value))
        return DriverResult()

    def fill(self, locator: LocatorSpec, value: str) -> DriverResult:
        return DriverResult()

    def select(self, locator: LocatorSpec, value: str) -> DriverResult:
        return DriverResult()

    def wait_visible(
        self,
        locator: LocatorSpec,
        timeout_seconds: float,
    ) -> DriverResult:
        return DriverResult()

    def wait_network_idle(self, timeout_seconds: float) -> DriverResult:
        return DriverResult()

    def screenshot(self, filename: str) -> Path:
        return Path(filename)

    def snapshot(self, filename: str, max_chars: int) -> str:
        return ""

    def state_save(self, path: Path) -> None:
        return None

    def state_load(self, path: Path) -> None:
        return None

    def current_url(self) -> str:
        return "https://example.test/page"

    def title(self) -> str:
        return "Page"

    def text(self, locator: LocatorSpec) -> str:
        return "value"


def test_agent_crawler_runs_recipe_with_fake_driver():
    driver = TranscriptDriver()
    recipe = Recipe(
        namespace="generic",
        key="sample",
        entrypoint=Entrypoint(url="https://example.test/page"),
        steps=[Step(id="open", action="goto")],
        observations={
            "value": ObservationSpec(
                id="value",
                kind="text",
                locator=LocatorSpec(kind="css", value=".value"),
                required=True,
            )
        },
        security_policy=SecurityPolicy(allowed_origins=["https://example.test"]),
    )

    result = AgentCrawler(driver).run(
        recipe,
        RunContext(session_id="run"),
    )

    assert result.ok is True
    assert result.output == {"value": "value"}
    assert driver.closed is True
    assert driver.calls == [
        ("open", "https://example.test/page"),
        ("goto", "https://example.test/page"),
    ]


def test_agent_crawler_ignores_driver_close_error():
    class CloseFailingDriver(TranscriptDriver):
        def close(self) -> None:
            self.closed = True
            raise BrowserDriverError("close timeout")

    driver = CloseFailingDriver()
    recipe = Recipe(
        namespace="generic",
        key="sample",
        entrypoint=Entrypoint(url="https://example.test/page"),
        observations={
            "value": ObservationSpec(
                id="value",
                kind="text",
                locator=LocatorSpec(kind="css", value=".value"),
                required=True,
            )
        },
        security_policy=SecurityPolicy(allowed_origins=["https://example.test"]),
    )

    result = AgentCrawler(driver).run(recipe, RunContext(session_id="run"))

    assert result.ok is True
    assert driver.closed is True
