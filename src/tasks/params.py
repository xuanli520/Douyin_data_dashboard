from pydantic import Field

from src.config import get_settings
from src.tasks.funboost_compat import BoosterParams, ConcurrentModeEnum


def _get_funboost_settings():
    return get_settings().funboost


class DouyinTaskParams(BoosterParams):
    broker_kind: str = Field(
        default_factory=lambda: _get_funboost_settings().broker_kind
    )
    max_retry_times: int = Field(
        default_factory=lambda: _get_funboost_settings().default_max_retry_times
    )
    retry_interval: int = Field(
        default_factory=lambda: _get_funboost_settings().default_retry_interval
    )
    function_timeout: int = Field(
        default_factory=lambda: _get_funboost_settings().default_function_timeout
    )
    is_using_rpc_mode: bool = False
    broker_exclusive_config: dict = Field(
        default_factory=lambda: {
            "pull_msg_batch_size": _get_funboost_settings().pull_msg_batch_size
        }
    )


class CollectionTaskParams(DouyinTaskParams):
    qps: float = 0.5
    concurrent_num: int = 200
    concurrent_mode: str = ConcurrentModeEnum.THREADING


class EtlTaskParams(DouyinTaskParams):
    qps: float = 10
    concurrent_num: int = 1
    concurrent_mode: str = ConcurrentModeEnum.SINGLE_THREAD
