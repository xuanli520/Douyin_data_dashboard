import subprocess

from src.core.agent.drivers.playwright_cli import PlaywrightCLIDriver
from src.core.agent.models import LocatorSpec


def test_cli_driver_wraps_subprocess_commands(tmp_path):
    commands: list[list[str]] = []

    def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                "### Page\n- Page URL: https://example.test\n- Page Title: Example\n"
            ),
            stderr="",
        )

    driver = PlaywrightCLIDriver(
        executable="playwright-cli",
        session_id="session-1",
        artifact_dir=tmp_path,
        run_command=run_command,
    )

    driver.open("https://example.test", headed=True)
    driver.click(LocatorSpec(kind="css", value="#submit"))
    driver.snapshot("page.yml", 100)
    driver.close()

    assert commands == [
        ["playwright-cli", "-s=session-1", "open", "https://example.test", "--headed"],
        ["playwright-cli", "-s=session-1", "click", "#submit"],
        [
            "playwright-cli",
            "-s=session-1",
            "snapshot",
            f"--filename={tmp_path / 'page.yml'}",
        ],
        ["playwright-cli", "-s=session-1", "close"],
    ]
    assert driver.current_url() == "https://example.test"
    assert driver.title() == "Example"


def test_cli_driver_loads_storage_state_in_same_session(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")
    commands: list[list[str]] = []

    def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    driver = PlaywrightCLIDriver(
        session_id="session-2",
        storage_state_path=state_path,
        run_command=run_command,
    )

    driver.open("https://example.test")

    assert commands == [
        ["playwright-cli", "-s=session-2", "open"],
        ["playwright-cli", "-s=session-2", "state-load", str(state_path)],
        ["playwright-cli", "-s=session-2", "goto", "https://example.test"],
    ]


def test_cli_driver_extract_text_uses_run_code(tmp_path):
    commands: list[list[str]] = []

    def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='### Result\n"hello"\n',
            stderr="",
        )

    driver = PlaywrightCLIDriver(
        executable="playwright-cli",
        session_id="session-3",
        artifact_dir=tmp_path,
        run_command=run_command,
    )

    result = driver.extract_text(LocatorSpec(kind="css", value="body"))

    assert result.data == {"text": "hello"}
    assert commands[0][:3] == ["playwright-cli", "-s=session-3", "run-code"]
    assert "innerText" in commands[0][3]


def test_cli_driver_wait_network_idle_waits_before_snapshot(tmp_path):
    commands: list[list[str]] = []

    def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                "### Page\n- Page URL: https://example.test\n- Page Title: Example\n"
            ),
            stderr="",
        )

    driver = PlaywrightCLIDriver(
        executable="playwright-cli",
        session_id="session-4",
        artifact_dir=tmp_path,
        run_command=run_command,
    )

    driver.wait_network_idle(3)

    assert commands[0][:3] == ["playwright-cli", "-s=session-4", "run-code"]
    assert "waitForLoadState('networkidle'" in commands[0][3]
    assert commands[1] == ["playwright-cli", "-s=session-4", "snapshot"]


def test_cli_driver_scroll_down_uses_run_code(tmp_path):
    commands: list[list[str]] = []

    def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    driver = PlaywrightCLIDriver(
        executable="playwright-cli",
        session_id="session-5",
        artifact_dir=tmp_path,
        run_command=run_command,
    )

    result = driver.scroll_down(300)

    assert result.data == {"amount": 300}
    assert commands[0][:3] == ["playwright-cli", "-s=session-5", "run-code"]
    assert "mouse.wheel(0, 300)" in commands[0][3]
    assert commands[1] == ["playwright-cli", "-s=session-5", "snapshot"]
