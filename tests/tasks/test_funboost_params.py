from src.config import get_settings
from src.tasks.params import CollectionTaskParams, DouyinTaskParams, EtlTaskParams


def test_douyin_task_params_reads_settings_defaults():
    get_settings.cache_clear()
    params = DouyinTaskParams(queue_name="q-default")
    settings = get_settings().funboost

    assert params.broker_kind == settings.broker_kind
    assert params.max_retry_times == settings.default_max_retry_times
    assert params.retry_interval == settings.default_retry_interval
    assert params.function_timeout == settings.default_function_timeout
    assert params.broker_exclusive_config["pull_msg_batch_size"] == 1


def test_collection_task_params_overrides_concurrency_fields():
    params = CollectionTaskParams(queue_name="q-collection")

    assert params.concurrent_mode == "THREADING"
    assert params.concurrent_num == 200
    assert params.qps == 0.5


def test_shop_dashboard_collection_params_and_metrics_targets():
    params = CollectionTaskParams(queue_name="collection_shop_dashboard")

    assert params.qps == 0.5
    assert params.concurrent_num == 150
    assert params.max_retry_times >= 3


def test_etl_task_params_overrides_concurrency_fields():
    params = EtlTaskParams(queue_name="q-etl")

    assert params.concurrent_mode == "SINGLE_THREAD"
    assert params.concurrent_num == 1
    assert params.qps == 10
