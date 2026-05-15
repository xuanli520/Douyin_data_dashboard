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
                "### Page\n"
                "- Page URL: https://example.test\n"
                "- Page Title: Example\n"
            ),
            stderr="",
        )

    driver = PlaywrightCLIDriver(
        executable="playwright-cli",
        artifact_dir=tmp_path,
        run_command=run_command,
    )

    driver.open("https://example.test", headed=True)
    driver.click(LocatorSpec(kind="css", value="#submit"))
    driver.snapshot("page.yml", 100)
    driver.close()

    assert commands == [
        ["playwright-cli", "open", "https://example.test", "--headed"],
        ["playwright-cli", "click", "#submit"],
        ["playwright-cli", "snapshot", f"--filename={tmp_path / 'page.yml'}"],
        ["playwright-cli", "close"],
    ]
    assert driver.current_url() == "https://example.test"
    assert driver.title() == "Example"
