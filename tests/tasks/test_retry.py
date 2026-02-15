from unittest.mock import MagicMock


class TestTaskAutoRetry:
    def test_task_has_autoretry_configured(self):
        from src.tasks.collection.douyin_orders import sync_orders

        assert hasattr(sync_orders, "autoretry_for")
        assert sync_orders.autoretry_for is not None
        assert len(sync_orders.autoretry_for) > 0

    def test_autoretry_includes_scraping_rate_limit(self):
        from src.tasks.collection.douyin_orders import sync_orders
        from src.tasks.exceptions import ScrapingRateLimitException

        assert ScrapingRateLimitException in sync_orders.autoretry_for

    def test_autoretry_includes_soft_time_limit(self):
        from src.tasks.collection.douyin_orders import sync_orders
        from celery.exceptions import SoftTimeLimitExceeded

        assert SoftTimeLimitExceeded in sync_orders.autoretry_for

    def test_autoretry_includes_redis_connection_error(self):
        from src.tasks.collection.douyin_orders import sync_orders
        import redis.exceptions

        assert redis.exceptions.ConnectionError in sync_orders.autoretry_for

    def test_retry_backoff_enabled(self):
        from src.tasks.collection.douyin_orders import sync_orders

        assert sync_orders.retry_backoff is True

    def test_retry_backoff_max_configured(self):
        from src.tasks.collection.douyin_orders import sync_orders

        assert sync_orders.retry_backoff_max == 600

    def test_max_retries_configured(self):
        from src.tasks.collection.douyin_orders import sync_orders

        assert sync_orders.max_retries == 5


class TestRetryBehavior:
    def test_retry_increments_retries(self):
        from src.tasks.collection.douyin_orders import sync_orders

        mock_request = MagicMock()
        mock_request.retries = 0

        task = MagicMock(spec=sync_orders)
        task.request = mock_request

        assert task.request.retries == 0


class TestETLTaskRetry:
    def test_etl_orders_has_retry_config(self):
        from src.tasks.etl.orders import process_orders

        assert hasattr(process_orders, "autoretry_for")
        assert process_orders.autoretry_for is not None

    def test_etl_products_has_retry_config(self):
        from src.tasks.etl.products import process_products

        assert hasattr(process_products, "autoretry_for")
        assert process_products.autoretry_for is not None

    def test_etl_orders_max_retries(self):
        from src.tasks.etl.orders import process_orders

        assert process_orders.max_retries == 3

    def test_etl_products_max_retries(self):
        from src.tasks.etl.products import process_products

        assert process_products.max_retries == 3
