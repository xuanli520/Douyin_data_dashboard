def test_shop_dashboard_dead_letter_handlers_return_recorded_payload():
    from src.tasks.collection.douyin_shop_dashboard import (
        handle_collection_shop_dashboard_dead_letter,
    )

    dashboard_payload = {"task_id": "t-1", "error": "http failed"}
    dashboard_result = handle_collection_shop_dashboard_dead_letter(
        **dashboard_payload,
    )
    assert dashboard_result["status"] == "recorded"
    assert dashboard_result["queue"] == "collection_shop_dashboard_dlx"
