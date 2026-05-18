from src.scrapers.shop_dashboard.login_state_manager import LoginStateManager
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore


async def test_login_state_manager_marks_expired_when_state_missing(tmp_path):
    store = SessionStateStore(base_dir=tmp_path)
    mgr = LoginStateManager(state_store=store)
    assert await mgr.check_and_refresh("acct-1") is False


async def test_login_state_manager_can_mark_active_after_expiration(tmp_path):
    store = SessionStateStore(base_dir=tmp_path)
    mgr = LoginStateManager(state_store=store)

    await mgr.mark_expired("acct-1", "expired")
    await mgr.mark_active("acct-1")

    state = await mgr._get_state("acct-1")
    assert state["status"] == "active"
    assert state["reason"] == ""
