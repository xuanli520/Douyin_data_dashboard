from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from src.scrapers.shop_dashboard.session_state_store import SessionStateStore


def bootstrap_login(
    *,
    page: Any,
    account_id: str,
    state_store: SessionStateStore,
    login_url: str = "https://fxg.jinritemai.com/login/common",
) -> Path:
    page.goto(login_url, wait_until="domcontentloaded")
    page.wait_for_url("**/fxg.jinritemai.com/compass/**", timeout=300000)
    return state_store.save(account_id, page.context.storage_state())


def run_bootstrap(
    *,
    account_id: str,
    state_dir: str | Path,
    headless: bool = False,
    login_url: str = "https://fxg.jinritemai.com/login/common",
) -> Path:
    from playwright.sync_api import sync_playwright

    store = SessionStateStore(base_dir=state_dir)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        saved_path = bootstrap_login(
            page=page,
            account_id=account_id,
            state_store=store,
            login_url=login_url,
        )
        context.close()
        browser.close()
    return saved_path


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
