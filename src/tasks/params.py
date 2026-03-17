from pydantic import Field, model_validator

from src.config import get_settings
from src.tasks.funboost_compat import BoosterParams, ConcurrentModeEnum


def _get_funboost_settings():
    return get_settings().funboost


def _booster_param_fields() -> set[str]:
    model_fields = getattr(BoosterParams, "model_fields", None)
    if isinstance(model_fields, dict):
        return {str(name) for name in model_fields}
    legacy_fields = getattr(BoosterParams, "__fields__", None)
    if isinstance(legacy_fields, dict):
        return {str(name) for name in legacy_fields}
    return set()


_BOOSTER_PARAM_FIELDS = _booster_param_fields()


class DouyinTaskParams(BoosterParams):
    broker_kind: str = Field(
        default_factory=lambda: _get_funboost_settings().broker_kind
    )
    max_retry_times: int = Field(
        default_factory=lambda: _get_funboost_settings().default_max_retry_times
    )
    if "retry_interval" in _BOOSTER_PARAM_FIELDS:
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

    @model_validator(mode="after")
    def _apply_shop_dashboard_overrides(self) -> "CollectionTaskParams":
        if self.queue_name != "collection_shop_dashboard":
            return self
        funboost_settings = _get_funboost_settings()
        self.qps = float(funboost_settings.shop_dashboard_collection_qps)
        self.concurrent_num = int(
            funboost_settings.shop_dashboard_collection_concurrent_num
        )
        self.max_retry_times = max(
            int(self.max_retry_times),
            int(funboost_settings.shop_dashboard_collection_max_retry_times),
        )
        return self


class EtlTaskParams(DouyinTaskParams):
    qps: float = 10
    concurrent_num: int = 1
    concurrent_mode: str = ConcurrentModeEnum.SINGLE_THREAD
