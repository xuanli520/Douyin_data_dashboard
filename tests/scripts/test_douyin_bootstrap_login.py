from unittest import mock

from src.scrapers.shop_dashboard.session_state_store import SessionStateStore

from scripts.douyin_bootstrap_login import bootstrap_login


def test_bootstrap_waits_for_compass_and_saves_state(tmp_path):
    page = mock.Mock()
    page.context.storage_state.return_value = {"cookies": [], "origins": []}
    store = SessionStateStore(base_dir=tmp_path)

    bootstrap_login(page=page, account_id="acct-1", state_store=store)

    page.wait_for_url.assert_called_once_with(
        "**/fxg.jinritemai.com/compass/**",
        timeout=300000,
    )
    assert store.exists("acct-1") is True
