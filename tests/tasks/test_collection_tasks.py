def test_sync_shop_dashboard_queue_and_retry_params():
    from src.tasks.collection.douyin_shop_dashboard import sync_shop_dashboard

    assert sync_shop_dashboard.boost_params.queue_name == "collection_shop_dashboard"
    assert (
        sync_shop_dashboard.boost_params.is_push_to_dlx_queue_when_retry_max_times
        is True
    )


def test_sync_shop_dashboard_agent_queue_and_retry_params():
    from src.tasks.collection.douyin_shop_agent import sync_shop_dashboard_agent

    assert (
        sync_shop_dashboard_agent.boost_params.queue_name
        == "collection_shop_dashboard_agent"
    )
    assert (
        sync_shop_dashboard_agent.boost_params.is_push_to_dlx_queue_when_retry_max_times
        is True
    )


def test_sync_shop_dashboard_agent_dead_letter_queue_and_retry_params():
    from src.tasks.collection.douyin_shop_agent import (
        handle_collection_shop_dashboard_agent_dead_letter,
    )

    assert (
        handle_collection_shop_dashboard_agent_dead_letter.boost_params.queue_name
        == "collection_shop_dashboard_agent_dlx"
    )
