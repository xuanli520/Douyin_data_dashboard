from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path
from typing import Any

from src.scrapers.shop_dashboard.session_state_store import SessionStateStore


def run_bootstrap(
    *,
    account_id: str,
    state_dir: str | Path,
    headless: bool = False,
    login_url: str = "https://fxg.jinritemai.com/login/common",
    session_name: str | None = None,
    timeout_seconds: float = 300.0,
    poll_interval_seconds: float = 1.0,
    runner: Any | None = None,
) -> Path:
    store = SessionStateStore(base_dir=state_dir)
    saved_path = store._path(account_id)
    cli_runner = runner or _run_playwright_cli
    session = str(session_name or f"bootstrap-{account_id}").replace("/", "_")
    open_command = _session_command(session, "open", login_url)
    if not headless:
        open_command.append("--headed")
    cli_runner(open_command)
    _wait_for_login_success(
        session=session,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        runner=cli_runner,
    )
    saved_path.parent.mkdir(parents=True, exist_ok=True)
    cli_runner(_session_command(session, "state-save", str(saved_path)))
    cli_runner(_session_command(session, "close"))
    return saved_path


def _run_playwright_cli(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result


def _session_command(session: str, command: str, *args: str) -> list[str]:
    return ["playwright-cli", f"-s={session}", command, *args]


def _wait_for_login_success(
    *,
    session: str,
    timeout_seconds: float,
    poll_interval_seconds: float,
    runner: Any,
) -> None:
    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    while time.monotonic() <= deadline:
        result = runner(_session_command(session, "snapshot"))
        current_url = _extract_page_url(result.stdout)
        if current_url and not _is_login_url(current_url):
            return
        time.sleep(max(poll_interval_seconds, 0.1))
    raise TimeoutError("login bootstrap timed out")


def _extract_page_url(snapshot: str) -> str:
    for line in snapshot.splitlines():
        stripped = line.strip()
        if stripped.startswith("- Page URL:"):
            return stripped.split(":", 1)[1].strip()
    return ""


def _is_login_url(url: str) -> bool:
    lowered = str(url or "").lower()
    return any(token in lowered for token in ("login/common", "/login", "passport"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap douyin login session state")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--state-dir", default=".runtime/shop_dashboard_state")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--login-url", default="https://fxg.jinritemai.com/login/common"
    )
    args = parser.parse_args()
    run_bootstrap(
        account_id=args.account_id,
        state_dir=args.state_dir,
        headless=args.headless,
        login_url=args.login_url,
    )


if __name__ == "__main__":
    main()
