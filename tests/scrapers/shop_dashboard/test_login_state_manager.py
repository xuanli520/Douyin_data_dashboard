from src.scrapers.shop_dashboard.login_state_manager import LoginStateManager
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore


async def test_login_state_manager_marks_expired_when_state_missing(tmp_path):
    store = SessionStateStore(base_dir=tmp_path)
    mgr = LoginStateManager(state_store=store)
    assert await mgr.check_and_refresh("acct-1") is False
