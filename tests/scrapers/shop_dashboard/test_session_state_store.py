from src.scrapers.shop_dashboard.session_state_store import SessionStateStore


def test_state_store_can_extract_cookie_mapping(tmp_path):
    store = SessionStateStore(base_dir=tmp_path)
    store.save("acct-1", {"cookies": [{"name": "sid", "value": "v"}], "origins": []})

    cookies = store.load_cookie_mapping("acct-1")
    assert cookies["sid"] == "v"


def test_state_store_saves_raw_playwright_shop_state(tmp_path):
    store = SessionStateStore(base_dir=tmp_path)
    state = {"cookies": [{"name": "sid", "value": "abc"}], "origins": []}

    path = store.save_playwright_state("acct/1", state, "shop/1")

    assert path == tmp_path / "playwright_states" / "acct_1" / "shop_1.json"
    assert store.exists_playwright_state("acct/1", "shop/1") is True
    assert store.load_playwright_state("acct/1", "shop/1") == state
