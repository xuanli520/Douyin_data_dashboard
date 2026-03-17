from src.scrapers.shop_dashboard.session_state_store import SessionStateStore


def test_state_store_can_extract_cookie_mapping(tmp_path):
    store = SessionStateStore(base_dir=tmp_path)
    store.save("acct-1", {"cookies": [{"name": "sid", "value": "v"}], "origins": []})

    cookies = store.load_cookie_mapping("acct-1")
    assert cookies["sid"] == "v"
