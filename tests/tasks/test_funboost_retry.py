def test_shop_dashboard_collection_retry_and_dlx_params():
    from src.tasks.collection.douyin_shop_dashboard import (
        handle_collection_shop_dashboard_dead_letter,
        sync_shop_dashboard,
    )

    assert sync_shop_dashboard.boost_params.queue_name == "collection_shop_dashboard"
    assert sync_shop_dashboard.boost_params.max_retry_times >= 3
    assert (
        sync_shop_dashboard.boost_params.is_push_to_dlx_queue_when_retry_max_times
        is True
    )
    assert (
        handle_collection_shop_dashboard_dead_letter.boost_params.queue_name
        == "collection_shop_dashboard_dlx"
    )
