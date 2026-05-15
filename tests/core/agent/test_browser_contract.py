from pathlib import Path

from src.core.agent.artifacts import build_artifact_path
from src.core.agent.browser import DriverResult
from src.core.agent.exceptions import BrowserDriverError
from src.core.agent.models import LocatorSpec


class FakeDriver:
    def open(self, url: str | None = None, *, headed: bool = False) -> None:
        if url == "boom":
            raise RuntimeError("boom")

    def close(self) -> None:
        return None

    def goto(self, url: str) -> DriverResult:
        return DriverResult(data={"url": url})

    def back(self) -> DriverResult:
        return DriverResult()

    def reload(self) -> DriverResult:
        return DriverResult()

    def click(self, locator: LocatorSpec) -> DriverResult:
        return DriverResult(data={"locator": locator.value})

    def fill(self, locator: LocatorSpec, value: str) -> DriverResult:
        return DriverResult(data={"locator": locator.value, "value": value})

    def select(self, locator: LocatorSpec, value: str) -> DriverResult:
        return DriverResult(data={"locator": locator.value, "value": value})

    def wait_visible(
        self,
        locator: LocatorSpec,
        timeout_seconds: float,
    ) -> DriverResult:
        return DriverResult(data={"locator": locator.value, "timeout": timeout_seconds})

    def wait_network_idle(self, timeout_seconds: float) -> DriverResult:
        return DriverResult(data={"timeout": timeout_seconds})

    def screenshot(self, filename: str) -> Path:
        return Path(filename)

    def snapshot(self, filename: str, max_chars: int) -> str:
        return filename[:max_chars]

    def state_save(self, path: Path) -> None:
        return None

    def state_load(self, path: Path) -> None:
        return None

    def current_url(self) -> str:
        return "https://allowed.test"

    def title(self) -> str:
        return "Allowed"

    def text(self, locator: LocatorSpec) -> str:
        return locator.value


def test_artifact_path_stays_under_root(tmp_path):
    target = build_artifact_path(tmp_path, "session", "shot.png")

    assert target == tmp_path / "session" / "shot.png"


def test_driver_errors_can_be_wrapped():
    driver = FakeDriver()

    try:
        driver.open("boom")
    except Exception as exc:
        wrapped = BrowserDriverError(str(exc))
    else:
        raise AssertionError("expected fake driver to fail")

    assert isinstance(wrapped, BrowserDriverError)
