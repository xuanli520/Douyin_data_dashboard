from src.scrapers.shop_dashboard.session_state_store import SessionStateStore


def test_state_store_load_returns_none_when_missing(tmp_path):
    store = SessionStateStore(base_dir=tmp_path)
    assert store.load("missing-account") is None


def test_state_store_exists_returns_false_when_missing(tmp_path):
    store = SessionStateStore(base_dir=tmp_path)
    assert store.exists("missing-account") is False
