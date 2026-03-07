from src.scrapers.shop_dashboard.login_state_manager import LoginStateManager
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore


async def test_login_state_manager_marks_expired_when_refresh_fails(tmp_path):
    store = SessionStateStore(base_dir=tmp_path)
    store.save("acct-1", {"cookies": [{"name": "sid", "value": "v"}], "origins": []})

    async def refresh_checker(_account_id: str) -> bool:
        return False

    mgr = LoginStateManager(state_store=store, refresh_checker=refresh_checker)

    assert await mgr.check_and_refresh("acct-1") is False


async def test_login_state_manager_returns_true_when_state_exists_and_refresh_ok(
    tmp_path,
):
    store = SessionStateStore(base_dir=tmp_path)
    store.save("acct-2", {"cookies": [{"name": "sid", "value": "v2"}], "origins": []})

    async def refresh_checker(_account_id: str) -> bool:
        return True

    mgr = LoginStateManager(state_store=store, refresh_checker=refresh_checker)

    assert await mgr.check_and_refresh("acct-2") is True
