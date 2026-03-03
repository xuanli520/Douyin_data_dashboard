from __future__ import annotations

import time

from src.tasks.collection.douyin_orders import sync_orders
from src.tasks.collection.douyin_products import sync_products
from src.tasks.funboost_compat import ApsJobAdder


def register_jobs() -> None:
    orders_job = ApsJobAdder(sync_orders, job_store_kind="redis")
    orders_job.add_push_job(
        trigger="cron",
        hour=2,
        minute=0,
        kwargs={"shop_id": "all", "date": "yesterday"},
        id="daily_collection_orders_sync",
    )

    products_job = ApsJobAdder(sync_products, job_store_kind="redis")
    products_job.add_push_job(
        trigger="cron",
        hour=2,
        minute=30,
        kwargs={"shop_id": "all", "date": "yesterday"},
        id="daily_collection_products_sync",
    )


def main() -> None:
    register_jobs()
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
