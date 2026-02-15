from celery.exceptions import SoftTimeLimitExceeded
import redis.exceptions
from loguru import logger

from src.tasks.celery_app import celery_app
from src.tasks.base import BaseTask, run_with_timeout_protection


@celery_app.task(
    bind=True,
    base=BaseTask,
    autoretry_for=(
        SoftTimeLimitExceeded,
        redis.exceptions.ConnectionError,
    ),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=5,
)
@run_with_timeout_protection
def sync_products(self, shop_id: str, triggered_by: int = None):
    logger.bind(
        task_id=self.request.id,
        task_name=self.name,
        triggered_by=triggered_by,
        shop_id=shop_id,
    ).info("Starting product sync task")

    result = {"status": "success", "shop_id": shop_id}
    return result
