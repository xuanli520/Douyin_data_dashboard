import importlib
import subprocess
import sys
from unittest import mock

from src.scrapers.shop_dashboard.session_state_store import SessionStateStore

from scripts import douyin_bootstrap_login as module
from scripts.douyin_bootstrap_login import bootstrap_login


def test_bootstrap_waits_for_login_success_and_saves_state(tmp_path):
    page = mock.Mock()
    page.context.storage_state.return_value = {"cookies": [], "origins": []}
    store = SessionStateStore(base_dir=tmp_path)

    bootstrap_login(page=page, account_id="acct-1", state_store=store)

    page.wait_for_function.assert_called_once()
    args, kwargs = page.wait_for_function.call_args
    assert '!href.includes("/login/")' in args[0]
    assert kwargs["timeout"] == 300000
    assert store.exists("acct-1") is True


def test_run_bootstrap_returns_actual_saved_path(monkeypatch, tmp_path):
    commands: list[list[str]] = []

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[2] == "snapshot":
            stdout = "- Page URL: https://fxg.jinritemai.com/home\n"
        else:
            stdout = ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    saved = module.run_bootstrap(
        account_id="acct/1",
        state_dir=tmp_path,
        headless=True,
        runner=runner,
        poll_interval_seconds=0.1,
    )

    assert saved == tmp_path / "acct_1.json"
    assert commands == [
        [
            "playwright-cli",
            "-s=bootstrap-acct_1",
            "open",
            "https://fxg.jinritemai.com/login/common",
        ],
        ["playwright-cli", "-s=bootstrap-acct_1", "snapshot"],
        ["playwright-cli", "-s=bootstrap-acct_1", "state-save", str(saved)],
        ["playwright-cli", "-s=bootstrap-acct_1", "close"],
    ]


def test_import_douyin_bootstrap_login_without_python_playwright(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("playwright"):
            raise AssertionError("python playwright should not be imported")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _guarded_import)
    sys.modules.pop("scripts.douyin_bootstrap_login", None)

    imported = importlib.import_module("scripts.douyin_bootstrap_login")
    assert hasattr(imported, "run_bootstrap")
