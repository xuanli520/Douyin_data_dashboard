from src.scrapers.shop_dashboard.session_state_store import SessionStateStore


def test_state_store_load_returns_none_when_missing(tmp_path):
    store = SessionStateStore(base_dir=tmp_path)
    assert store.load("missing-account") is None


def test_state_store_exists_returns_false_when_missing(tmp_path):
    store = SessionStateStore(base_dir=tmp_path)
    assert store.exists("missing-account") is False


def test_state_store_load_returns_none_for_corrupted_json(tmp_path):
    store = SessionStateStore(base_dir=tmp_path)
    bad_file = tmp_path / "acct-1.json"
    bad_file.write_text("{bad-json", encoding="utf-8")

    assert store.load("acct-1") is None


def test_state_store_bundle_roundtrip(tmp_path):
    store = SessionStateStore(base_dir=tmp_path)
    store.save_bundle(
        "acct-1",
        "shop-1",
        {
            "cookies": {"sid": "token"},
            "common_query": {"msToken": "m1"},
            "validated_shop_id": "shop-1",
            "verified_actual_shop_id": "shop-1",
            "verify_status": "passed",
            "verified_at": "2026-03-10T00:00:00+00:00",
            "session_version": "2",
        },
    )

    bundle = store.load_bundle("acct-1", "shop-1")
    assert isinstance(bundle, dict)
    assert bundle["cookies"]["sid"] == "token"
    assert bundle["common_query"]["msToken"] == "m1"
    assert bundle["verify_status"] == "passed"
    assert bundle["verified_actual_shop_id"] == "shop-1"
    assert bundle["verified_at"] == "2026-03-10T00:00:00+00:00"
    assert bundle["session_version"] == "2"


def test_state_store_bundle_fields_are_normalized(tmp_path):
    store = SessionStateStore(base_dir=tmp_path)
    store.save_bundle(
        "acct-1",
        "shop-1",
        {
            "cookies": {"sid": 1},
            "common_query": {"msToken": "m1"},
        },
    )

    bundle = store.load_bundle("acct-1", "shop-1")
    assert isinstance(bundle, dict)
    assert bundle["verify_status"] == "unknown"
    assert bundle["verified_actual_shop_id"] == "shop-1"
    assert bundle["session_version"] == "1"
