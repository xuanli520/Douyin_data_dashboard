from __future__ import annotations

import argparse
from threading import Thread
from typing import Callable

from src.tasks.collection import douyin_shop_agent, douyin_shop_dashboard
from src.tasks.etl import orders as etl_orders
from src.tasks.etl import products as etl_products


def _queue_runners(etl_processes: int) -> dict[str, Callable[[], None]]:
    return {
        "collection_shop_dashboard": lambda: (
            douyin_shop_dashboard.sync_shop_dashboard.consume()
        ),
        "collection_shop_dashboard_agent": lambda: (
            douyin_shop_agent.sync_shop_dashboard_agent.consume()
        ),
        "etl_orders": lambda: etl_orders.process_orders.multi_process_consume(
            etl_processes
        ),
        "etl_products": lambda: etl_products.process_products.multi_process_consume(
            etl_processes
        ),
        "collection_shop_dashboard_dlx": lambda: (
            douyin_shop_dashboard.handle_collection_shop_dashboard_dead_letter.consume()
        ),
        "collection_shop_dashboard_agent_dlx": lambda: (
            douyin_shop_agent.handle_collection_shop_dashboard_agent_dead_letter.consume()
        ),
        "etl_orders_dlx": lambda: etl_orders.handle_etl_orders_dead_letter.consume(),
        "etl_products_dlx": lambda: (
            etl_products.handle_etl_products_dead_letter.consume()
        ),
    }


def run_all(etl_processes: int = 2) -> None:
    threads = [
        Thread(target=runner, name=f"worker-{queue_name}")
        for queue_name, runner in _queue_runners(etl_processes).items()
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def run_queue(queue_name: str, etl_processes: int = 2) -> None:
    runner = _queue_runners(etl_processes).get(queue_name)
    if runner is None:
        raise ValueError(f"unsupported queue name: {queue_name}")
    runner()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Funboost worker entrypoint")
    parser.add_argument("--queue", type=str, default=None, help="Optional queue name")
    parser.add_argument(
        "--etl-processes",
        type=int,
        default=2,
        help="Process count used by ETL workers",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.queue:
        run_queue(args.queue, etl_processes=args.etl_processes)
        return
    run_all(etl_processes=args.etl_processes)


if __name__ == "__main__":
    main()
