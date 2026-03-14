import importlib
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
    class _FakeContext:
        def new_page(self):
            return object()

        def close(self):
            return None

    class _FakeBrowser:
        def new_context(self):
            return _FakeContext()

        def close(self):
            return None

    class _FakePlaywright:
        class chromium:
            @staticmethod
            def launch(headless=False):  # noqa: ARG004
                return _FakeBrowser()

    class _FakePlaywrightContext:
        def __enter__(self):
            return _FakePlaywright()

        def __exit__(self, exc_type, exc, tb):  # noqa: ARG002
            return False

    def _fake_bootstrap_login(*, account_id, state_store, **_kwargs):
        return state_store.save(account_id, {"cookies": [], "origins": []})

    monkeypatch.setitem(
        sys.modules,
        "playwright.sync_api",
        type(
            "_SyncApiModule",
            (),
            {"sync_playwright": staticmethod(lambda: _FakePlaywrightContext())},
        )(),
    )
    monkeypatch.setattr(module, "bootstrap_login", _fake_bootstrap_login)

    saved = module.run_bootstrap(account_id="acct/1", state_dir=tmp_path, headless=True)

    assert saved == tmp_path / "acct_1.json"
    assert saved.exists() is True


def test_import_douyin_bootstrap_login_without_playwright_sync_api(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "playwright.sync_api":
            raise AssertionError("playwright.sync_api should be lazily imported")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _guarded_import)
    sys.modules.pop("scripts.douyin_bootstrap_login", None)

    imported = importlib.import_module("scripts.douyin_bootstrap_login")
    assert hasattr(imported, "run_bootstrap")
