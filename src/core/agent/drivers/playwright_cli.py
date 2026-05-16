from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from src.core.agent.browser import DriverResult
from src.core.agent.exceptions import BrowserDriverError
from src.core.agent.models import LocatorSpec


class PlaywrightCLIDriver:
    def __init__(
        self,
        *,
        executable: str = "playwright-cli",
        storage_state_path: str | Path | None = None,
        artifact_dir: str | Path = ".runtime/agent_artifacts",
        run_command: Callable[[list[str]], subprocess.CompletedProcess[str]]
        | None = None,
    ) -> None:
        self.executable = executable
        self.storage_state_path = (
            Path(storage_state_path) if storage_state_path else None
        )
        self.artifact_dir = Path(artifact_dir)
        self._run_command = run_command or self._default_run_command
        self._current_url = ""
        self._title = ""

    def open(self, url: str | None = None, *, headed: bool = False) -> None:
        command = ["open"]
        should_load_state = bool(
            self.storage_state_path and self.storage_state_path.exists()
        )
        if url and not should_load_state:
            command.append(url)
        if headed:
            command.append("--headed")
        self._run(command)
        if should_load_state:
            self.state_load(self.storage_state_path)
        if should_load_state and url:
            self.goto(url)

    def close(self) -> None:
        self._run(["close"])

    def goto(self, url: str) -> DriverResult:
        result = self._run(["goto", url])
        self._current_url = url
        self._capture_page_metadata(result.stdout)
        return DriverResult(data={"url": url})

    def back(self) -> DriverResult:
        self._capture_page_metadata(self._run(["go-back"]).stdout)
        return DriverResult()

    def reload(self) -> DriverResult:
        self._capture_page_metadata(self._run(["reload"]).stdout)
        return DriverResult()

    def click(self, locator: LocatorSpec) -> DriverResult:
        self._capture_page_metadata(self._run(["click", locator.value]).stdout)
        return DriverResult()

    def fill(self, locator: LocatorSpec, value: str) -> DriverResult:
        self._capture_page_metadata(self._run(["fill", locator.value, value]).stdout)
        return DriverResult()

    def select(self, locator: LocatorSpec, value: str) -> DriverResult:
        self._capture_page_metadata(self._run(["select", locator.value, value]).stdout)
        return DriverResult()

    def wait_visible(
        self,
        locator: LocatorSpec,
        timeout_seconds: float,
    ) -> DriverResult:
        _ = timeout_seconds
        self._capture_page_metadata(self._run(["snapshot", locator.value]).stdout)
        return DriverResult()

    def wait_network_idle(self, timeout_seconds: float) -> DriverResult:
        _ = timeout_seconds
        self._capture_page_metadata(self._run(["snapshot"]).stdout)
        return DriverResult()

    def scroll_down(self, amount: str | int | float | None = None) -> DriverResult:
        command = ["scroll-down"]
        if amount is not None:
            command.append(str(amount))
        self._capture_page_metadata(self._run(command).stdout)
        return DriverResult(data={"amount": amount})

    def scroll_up(self, amount: str | int | float | None = None) -> DriverResult:
        command = ["scroll-up"]
        if amount is not None:
            command.append(str(amount))
        self._capture_page_metadata(self._run(command).stdout)
        return DriverResult(data={"amount": amount})

    def scroll_to_element(self, locator: LocatorSpec) -> DriverResult:
        self._capture_page_metadata(
            self._run(["scroll-to-element", locator.value]).stdout
        )
        return DriverResult(data={"locator": locator.value})

    def extract_table(self, locator: LocatorSpec) -> DriverResult:
        text = self._run(["extract-table", locator.value]).stdout.strip()
        return DriverResult(data={"text": text})

    def extract_list(self, locator: LocatorSpec) -> DriverResult:
        text = self._run(["extract-list", locator.value]).stdout.strip()
        return DriverResult(
            data={"items": [item.strip() for item in text.splitlines() if item.strip()]}
        )

    def extract_text(self, locator: LocatorSpec) -> DriverResult:
        text = self._run(["extract-text", locator.value]).stdout.strip()
        return DriverResult(data={"text": text})

    def screenshot(self, filename: str) -> Path:
        target = self.artifact_dir / Path(filename).name
        target.parent.mkdir(parents=True, exist_ok=True)
        self._run(["screenshot", f"--filename={target}"])
        return target

    def snapshot(self, filename: str = "snapshot.yml", max_chars: int = 30000) -> str:
        target = self.artifact_dir / Path(filename).name
        target.parent.mkdir(parents=True, exist_ok=True)
        result = self._run(["snapshot", f"--filename={target}"])
        text = result.stdout[: max(max_chars, 0)]
        target.write_text(text, encoding="utf-8")
        return text

    def state_save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._run(["state-save", str(path)])

    def state_load(self, path: Path) -> None:
        self._run(["state-load", str(path)])
        self.storage_state_path = path

    def current_url(self) -> str:
        return self._current_url

    def get_current_url(self) -> str:
        return self.current_url()

    def title(self) -> str:
        return self._title

    def get_page_title(self) -> str:
        return self.title()

    def text(self, locator: LocatorSpec) -> str:
        return self._run(["snapshot", locator.value]).stdout.strip()

    def get_element_text(self, locator: LocatorSpec) -> str:
        return self.text(locator)

    def get_snapshot(self) -> str:
        return self.snapshot()

    def capture_screenshot(self) -> str:
        return str(self.screenshot("screenshot.png"))

    def take_screenshot(self) -> str:
        return self.capture_screenshot()

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        command = [self.executable, *args]
        try:
            result = self._run_command(command)
        except FileNotFoundError as exc:
            raise BrowserDriverError("playwright-cli executable was not found") from exc
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise BrowserDriverError(message or "playwright-cli command failed")
        return result

    def _default_run_command(
        self,
        command: list[str],
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
        )

    def _capture_page_metadata(self, text: str) -> None:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("- Page URL:"):
                self._current_url = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("- Page Title:"):
                self._title = stripped.split(":", 1)[1].strip()
