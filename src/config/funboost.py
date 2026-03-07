from pydantic_settings import BaseSettings


class FunboostSettings(BaseSettings):
    broker_kind: str = "REDIS_ACK_ABLE"
    queue_redis_db: int = 7
    filter_and_rpc_result_redis_db: int = 8
    status_ttl_seconds: int = 3600
    default_function_timeout: int = 3600
    default_max_retry_times: int = 3
    default_retry_interval: int = 60
    pull_msg_batch_size: int = 1
    shop_dashboard_collection_qps: float = 0.5
    shop_dashboard_collection_concurrent_num: int = 150
    shop_dashboard_collection_max_retry_times: int = 3
