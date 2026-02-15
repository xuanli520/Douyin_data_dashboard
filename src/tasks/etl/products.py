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
    max_retries=3,
)
@run_with_timeout_protection
def process_products(self, triggered_by: int = None):
    logger.bind(
        task_id=self.request.id,
        task_name=self.name,
        triggered_by=triggered_by,
    ).info("Starting product ETL task")

    result = {"status": "success"}
    return result
