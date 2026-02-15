from celery.signals import worker_process_init
from src.tasks.base import BaseTask


@worker_process_init.connect
def init_redis_connection(**kwargs):
    BaseTask._redis = None
    BaseTask._redis = BaseTask().sync_redis
    import logging

    logging.getLogger(__name__).info(
        f"Redis connection initialized for worker pid={kwargs.get('pid')}"
    )
