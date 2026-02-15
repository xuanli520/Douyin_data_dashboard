from src.tasks.celery_app import celery_app


class TestCeleryAppConfiguration:
    def test_include_explicit_registration(self):
        assert "src.tasks.collection.douyin_orders" in celery_app.conf.include
        assert "src.tasks.collection.douyin_products" in celery_app.conf.include
        assert "src.tasks.etl.orders" in celery_app.conf.include
        assert "src.tasks.etl.products" in celery_app.conf.include

    def test_timezone_config(self):
        assert celery_app.conf.timezone == "Asia/Shanghai"

    def test_enable_utc_config(self):
        assert celery_app.conf.enable_utc is False

    def test_visibility_timeout_consistency(self):
        visibility_timeout = celery_app.conf.visibility_timeout
        broker_visibility = celery_app.conf.broker_transport_options.get(
            "visibility_timeout"
        )
        result_visibility = celery_app.conf.result_backend_transport_options.get(
            "visibility_timeout"
        )

        assert visibility_timeout == 7200
        assert broker_visibility == 7200
        assert result_visibility == 7200

    def test_result_backend_key_prefix(self):
        global_keyprefix = celery_app.conf.result_backend_transport_options.get(
            "global_keyprefix"
        )
        assert global_keyprefix == "douyin:celery:"

    def test_beat_schedule_initial_empty(self):
        assert celery_app.conf.beat_schedule == {}

    def test_task_serializer_config(self):
        assert celery_app.conf.task_serializer == "json"
        assert "json" in celery_app.conf.accept_content

    def test_result_serializer_config(self):
        assert celery_app.conf.result_serializer == "json"

    def test_task_track_started(self):
        assert celery_app.conf.task_track_started is True

    def test_task_time_limits(self):
        assert celery_app.conf.task_time_limit == 3600
        assert celery_app.conf.task_soft_time_limit == 3000

    def test_worker_config(self):
        assert celery_app.conf.worker_prefetch_multiplier == 4
        assert celery_app.conf.worker_max_tasks_per_child == 1000

    def test_result_expires(self):
        assert celery_app.conf.result_expires == 604800

    def test_task_acks_late(self):
        assert celery_app.conf.task_acks_late is True

    def test_task_reject_on_worker_lost(self):
        assert celery_app.conf.task_reject_on_worker_lost is True
