def test_sync_shop_dashboard_queue_and_retry_params():
    from src.tasks.collection.douyin_shop_dashboard import sync_shop_dashboard

    assert sync_shop_dashboard.boost_params.queue_name == "collection_shop_dashboard"
    assert (
        sync_shop_dashboard.boost_params.is_push_to_dlx_queue_when_retry_max_times
        is True
    )
