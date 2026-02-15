from celery.exceptions import SoftTimeLimitExceeded
import redis.exceptions
from loguru import logger

from src.tasks.celery_app import celery_app
from src.tasks.base import BaseTask, run_with_timeout_protection
from src.tasks.exceptions import ScrapingRateLimitException


@celery_app.task(
    bind=True,
    base=BaseTask,
    autoretry_for=(
        ScrapingRateLimitException,
        SoftTimeLimitExceeded,
        redis.exceptions.ConnectionError,
    ),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=5,
)
@run_with_timeout_protection
def sync_orders(self, shop_id: str, date: str, triggered_by: int = None):
    logger.bind(
        task_id=self.request.id,
        task_name=self.name,
        triggered_by=triggered_by,
        shop_id=shop_id,
        date=date,
    ).info("Starting order sync task")

    result = {"status": "success", "shop_id": shop_id, "date": date}
    return result
