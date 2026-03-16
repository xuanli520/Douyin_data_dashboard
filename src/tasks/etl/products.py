from __future__ import annotations

import logging
from typing import Any

from src.tasks.base import TaskStatusMixin, write_started_status_safe
from src.tasks.exceptions import ScrapingFailedException
from src.tasks.funboost_compat import boost
from src.tasks.params import EtlTaskParams

logger = logging.getLogger(__name__)


@boost(
    EtlTaskParams(
        queue_name="etl_products",
        consumer_override_cls=TaskStatusMixin,
        is_push_to_dlx_queue_when_retry_max_times=True,
    )
)
def process_products(
    batch_date: str,
    triggered_by: int | None = None,
    execution_id: int | None = None,
) -> dict[str, Any]:
    write_started_status_safe(
        process_products,
        "process_products",
        triggered_by,
        logger=logger,
        execution_id=execution_id,
    )
    raise ScrapingFailedException(
        "ETL products task not implemented",
        error_data={
            "status": "failed",
            "reason": "not implemented",
            "task": "process_products",
            "batch_date": batch_date,
            "triggered_by": triggered_by,
            "execution_id": execution_id,
        },
    )


@boost(
    EtlTaskParams(
        queue_name="etl_products_dlx",
        consumer_override_cls=TaskStatusMixin,
    )
)
def handle_etl_products_dead_letter(**payload) -> dict[str, Any]:
    return {"status": "recorded", "queue": "etl_products_dlx", "payload": payload}
