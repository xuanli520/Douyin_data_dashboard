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
        self.storage_state_path = Path(storage_state_path) if storage_state_path else None
        self.artifact_dir = Path(artifact_dir)
        self._run_command = run_command or self._default_run_command
        self._current_url = ""
        self._title = ""

    def open(self, url: str | None = None, *, headed: bool = False) -> None:
        command = ["open"]
        if url:
            command.append(url)
        if headed:
            command.append("--headed")
        self._run(command)
        if self.storage_state_path and self.storage_state_path.exists():
            self.state_load(self.storage_state_path)

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

    def screenshot(self, filename: str) -> Path:
        target = self.artifact_dir / Path(filename).name
        target.parent.mkdir(parents=True, exist_ok=True)
        self._run(["screenshot", f"--filename={target}"])
        return target

    def snapshot(self, filename: str, max_chars: int) -> str:
        target = self.artifact_dir / Path(filename).name
        target.parent.mkdir(parents=True, exist_ok=True)
        result = self._run(["snapshot", f"--filename={target}"])
        text = result.stdout[:max(max_chars, 0)]
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

    def title(self) -> str:
        return self._title

    def text(self, locator: LocatorSpec) -> str:
        return self._run(["snapshot", locator.value]).stdout.strip()

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
