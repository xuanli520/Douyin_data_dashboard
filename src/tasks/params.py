from funboost import BoosterParams
from funboost.constant import ConcurrentModeEnum

from src.config import get_settings

_funboost_settings = get_settings().funboost


class DouyinTaskParams(BoosterParams):
    broker_kind: str = _funboost_settings.broker_kind
    max_retry_times: int = _funboost_settings.default_max_retry_times
    retry_interval: int = _funboost_settings.default_retry_interval
    function_timeout: int = _funboost_settings.default_function_timeout
    is_using_rpc_mode: bool = False
    broker_exclusive_config = {
        "pull_msg_batch_size": _funboost_settings.pull_msg_batch_size
    }


class CollectionTaskParams(DouyinTaskParams):
    qps: float = 0.5
    concurrent_num: int = 200
    concurrent_mode: str = ConcurrentModeEnum.THREADING


class EtlTaskParams(DouyinTaskParams):
    qps: float = 10
    concurrent_num: int = 1
    concurrent_mode: str = ConcurrentModeEnum.SINGLE_THREAD
