import logging

from funboost.utils.simple_data_class import DataClassBase

from src.config import get_settings

settings = get_settings()


class BrokerConnConfig(DataClassBase):
    REDIS_HOST = settings.cache.host
    REDIS_PORT = settings.cache.port
    REDIS_PASSWORD = settings.cache.password or ""
    REDIS_DB = settings.funboost.queue_redis_db
    REDIS_DB_FILTER_AND_RPC_RESULT = settings.funboost.filter_and_rpc_result_redis_db
    if REDIS_PASSWORD:
        REDIS_URL = (
            f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
        )
    else:
        REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"


class FunboostCommonConfig(DataClassBase):
    TIMEZONE = "Asia/Shanghai"
    NB_LOG_FORMATER_INDEX_FOR_CONSUMER_AND_PUBLISHER = 11
    FUNBOOST_PROMPT_LOG_LEVEL = logging.INFO
