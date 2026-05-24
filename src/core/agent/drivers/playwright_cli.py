from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from src.core.agent.browser import DriverResult
from src.core.agent.exceptions import BrowserDriverError
from src.core.agent.models import LocatorSpec


class PlaywrightCLIDriver:
    _DEFAULT_COMMAND_TIMEOUT_SECONDS = 60

    def __init__(
        self,
        *,
        executable: str = "playwright-cli",
        session_id: str | None = None,
        storage_state_path: str | Path | None = None,
        artifact_dir: str | Path = ".runtime/agent_artifacts",
        command_timeout_seconds: int = _DEFAULT_COMMAND_TIMEOUT_SECONDS,
        run_command: Callable[[list[str]], subprocess.CompletedProcess[str]]
        | None = None,
    ) -> None:
        self.executable = executable
        self._session_id = str(session_id or uuid4().hex)
        self.storage_state_path = (
            Path(storage_state_path) if storage_state_path else None
        )
        self.artifact_dir = Path(artifact_dir)
        self._command_timeout_seconds = max(int(command_timeout_seconds), 1)
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
        if locator.kind == "css":
            self._capture_page_metadata(self._run(["click", locator.value]).stdout)
        else:
            self._capture_page_metadata(
                self._run_code(f"await {_locator_expression(locator)}.click();").stdout
            )
        return DriverResult()

    def click_js(self, locator: LocatorSpec) -> DriverResult:
        expression = _locator_expression(locator)
        self._capture_page_metadata(
            self._run_code(
                f"const target = {expression};\n"
                "await target.waitFor({ state: 'attached', timeout: 5000 });\n"
                "await target.evaluate(element => element.click());\n"
                "await Promise.race([\n"
                "  page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => null),\n"
                "  page.waitForTimeout(3000),\n"
                "]);"
            ).stdout
        )
        return DriverResult()

    def check(self, locator: LocatorSpec) -> DriverResult:
        if locator.kind == "css":
            self._capture_page_metadata(self._run(["check", locator.value]).stdout)
        else:
            self._capture_page_metadata(
                self._run_code(f"await {_locator_expression(locator)}.check();").stdout
            )
        return DriverResult()

    def fill(self, locator: LocatorSpec, value: str) -> DriverResult:
        if locator.kind == "css":
            self._capture_page_metadata(
                self._run(["fill", locator.value, value]).stdout
            )
        else:
            self._capture_page_metadata(
                self._run_code(
                    f"await {_locator_expression(locator)}.fill({json.dumps(value)});"
                ).stdout
            )
        return DriverResult()

    def select(self, locator: LocatorSpec, value: str) -> DriverResult:
        if locator.kind == "css":
            self._capture_page_metadata(
                self._run(["select", locator.value, value]).stdout
            )
        else:
            self._capture_page_metadata(
                self._run_code(
                    f"await {_locator_expression(locator)}.selectOption({json.dumps(value)});"
                ).stdout
            )
        return DriverResult()

    def wait_visible(
        self,
        locator: LocatorSpec,
        timeout_seconds: float,
    ) -> DriverResult:
        timeout_milliseconds = max(int(float(timeout_seconds or 0) * 1000), 1)
        self._capture_page_metadata(
            self._run_code(
                f"await {_locator_expression(locator)}.waitFor({{ state: 'visible', timeout: {timeout_milliseconds} }});"
            ).stdout
        )
        return DriverResult()

    def wait_network_idle(self, timeout_seconds: float) -> DriverResult:
        timeout_milliseconds = max(int(float(timeout_seconds or 0) * 1000), 1)
        self._run_code(
            "await page.waitForLoadState('networkidle', "
            f"{{ timeout: {timeout_milliseconds} }}).catch(() => null);"
        )
        self._capture_page_metadata(self._run(["snapshot"]).stdout)
        return DriverResult()

    def scroll_down(self, amount: str | int | float | None = None) -> DriverResult:
        scroll_amount = _scroll_amount(amount, 600)
        self._run_code(
            f"await page.mouse.wheel(0, {scroll_amount});\n"
            "await page.waitForTimeout(200);"
        )
        self._capture_page_metadata(self._run(["snapshot"]).stdout)
        return DriverResult(data={"amount": amount})

    def scroll_up(self, amount: str | int | float | None = None) -> DriverResult:
        scroll_amount = _scroll_amount(amount, 600)
        self._run_code(
            f"await page.mouse.wheel(0, -{scroll_amount});\n"
            "await page.waitForTimeout(200);"
        )
        self._capture_page_metadata(self._run(["snapshot"]).stdout)
        return DriverResult(data={"amount": amount})

    def scroll_to_element(self, locator: LocatorSpec) -> DriverResult:
        self._run_code(f"await {_locator_expression(locator)}.scrollIntoViewIfNeeded();")
        self._capture_page_metadata(self._run(["snapshot"]).stdout)
        return DriverResult(data={"locator": locator.value})

    def extract_table(self, locator: LocatorSpec) -> DriverResult:
        text = self.text(locator)
        return DriverResult(data={"text": text})

    def extract_list(self, locator: LocatorSpec) -> DriverResult:
        text = self.text(locator)
        return DriverResult(
            data={"items": [item.strip() for item in text.splitlines() if item.strip()]}
        )

    def extract_text(self, locator: LocatorSpec) -> DriverResult:
        text = self.text(locator)
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
        result = self._run_code(
            f"return await {_locator_expression(locator)}.innerText();"
        )
        return _cli_result_text(result.stdout)

    def get_element_text(self, locator: LocatorSpec) -> str:
        return self.text(locator)

    def get_snapshot(self) -> str:
        return self.snapshot()

    def capture_screenshot(self) -> str:
        return str(self.screenshot("screenshot.png"))

    def take_screenshot(self) -> str:
        return self.capture_screenshot()

    def input_value(self, locator: LocatorSpec) -> str:
        result = self._run_code(
            f"return await {_locator_expression(locator)}.inputValue();"
        )
        return _cli_result_text(result.stdout)

    def page_text(self) -> str:
        result = self._run_code("return await page.locator('body').innerText();")
        return _cli_result_text(result.stdout)

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        command = [self.executable, f"-s={self._session_id}", *args]
        try:
            result = self._run_command(command)
        except FileNotFoundError as exc:
            raise BrowserDriverError("playwright-cli executable was not found") from exc
        except subprocess.TimeoutExpired as exc:
            raise BrowserDriverError(
                f"playwright-cli command timed out after {exc.timeout} seconds"
            ) from exc
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise BrowserDriverError(message or "playwright-cli command failed")
        error_message = _cli_error_message(result)
        if error_message:
            raise BrowserDriverError(error_message)
        return result

    def _run_code(self, code: str) -> subprocess.CompletedProcess[str]:
        return self._run(["run-code", f"async page => {{\n{code}\n}}"])

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
            timeout=self._command_timeout_seconds,
        )

    def _capture_page_metadata(self, text: str) -> None:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("- Page URL:"):
                self._current_url = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("- Page Title:"):
                self._title = stripped.split(":", 1)[1].strip()


def _locator_expression(locator: LocatorSpec) -> str:
    if locator.kind == "css":
        return f"page.locator({json.dumps(locator.value)})"
    if locator.kind == "xpath":
        value = (
            locator.value
            if locator.value.startswith("xpath=")
            else f"xpath={locator.value}"
        )
        return f"page.locator({json.dumps(value)})"
    if locator.kind == "text":
        return f"page.getByText({json.dumps(locator.value)}, {{ exact: true }}).first()"
    if locator.kind == "role":
        role, name = _role_parts(locator.value)
        if name:
            return f"page.getByRole({json.dumps(role)}, {{ name: {json.dumps(name)} }}).first()"
        return f"page.getByRole({json.dumps(role)}).first()"
    raise BrowserDriverError(f"unsupported locator kind: {locator.kind}")


def _scroll_amount(value: str | int | float | None, default: int) -> int:
    try:
        return abs(int(float(value))) if value is not None else default
    except (TypeError, ValueError):
        return default


def _role_parts(value: str) -> tuple[str, str]:
    normalized = value.strip()
    role, _, name = normalized.partition(" ")
    name = name.strip()
    if len(name) >= 2 and name[0] == '"' and name[-1] == '"':
        name = name[1:-1]
    return role, name


def _cli_error_message(result: subprocess.CompletedProcess[str]) -> str:
    output = "\n".join(item for item in (result.stdout, result.stderr) if item)
    lines = [line.strip() for line in output.splitlines()]
    if "### Error" not in lines:
        return ""
    index = lines.index("### Error")
    for line in lines[index + 1 :]:
        if line and not line.startswith("### "):
            return line
    return "playwright-cli command failed"


def _cli_result_text(stdout: str) -> str:
    lines = stdout.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "### Result":
            continue
        payload: list[str] = []
        for item in lines[index + 1 :]:
            if item.startswith("### "):
                break
            payload.append(item)
        raw = "\n".join(payload).strip()
        if not raw:
            return ""
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        return str(parsed)
    return stdout.strip()
