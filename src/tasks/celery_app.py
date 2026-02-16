from celery import Celery
from celery.signals import worker_process_init
from src.config import get_settings
from src.tasks.base import BaseTask


settings = get_settings()

celery_app = Celery(
    "douyin_dashboard",
    broker=settings.celery.broker_url or settings.cache.url,
    backend=settings.celery.result_backend or settings.cache.url,
    include=[
        "src.tasks.collection.douyin_orders",
        "src.tasks.collection.douyin_products",
        "src.tasks.etl.orders",
        "src.tasks.etl.products",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3000,
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,
    result_expires=604800,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_deduplicate_successful_tasks=True,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    visibility_timeout=7200,
    broker_transport_options={"visibility_timeout": 7200},
    result_backend_transport_options={
        "visibility_timeout": 7200,
        "global_keyprefix": "douyin:celery:",
    },
    beat_schedule={},
    task_routes={
        "src.tasks.collection.*": {"queue": "collection"},
        "src.tasks.etl.*": {"queue": "etl"},
    },
)


@worker_process_init.connect
def init_redis_connection(**kwargs):
    from src.tasks.base import create_redis_connection

    BaseTask._redis = None
    BaseTask._redis = create_redis_connection()
    import logging

    logging.getLogger(__name__).info(
        f"Redis connection initialized for worker pid={kwargs.get('pid')}"
    )
