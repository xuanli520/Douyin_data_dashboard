from __future__ import annotations

import argparse

from src.tasks.collection import douyin_orders, douyin_products
from src.tasks.etl import orders as etl_orders
from src.tasks.etl import products as etl_products


def run_all(etl_processes: int = 2) -> None:
    douyin_orders.sync_orders.consume()
    douyin_products.sync_products.consume()
    etl_orders.process_orders.multi_process_consume(etl_processes)
    etl_products.process_products.multi_process_consume(etl_processes)


def run_queue(queue_name: str, etl_processes: int = 2) -> None:
    if queue_name == "collection_orders":
        douyin_orders.sync_orders.consume()
        return
    if queue_name == "collection_products":
        douyin_products.sync_products.consume()
        return
    if queue_name == "etl_orders":
        etl_orders.process_orders.multi_process_consume(etl_processes)
        return
    if queue_name == "etl_products":
        etl_products.process_products.multi_process_consume(etl_processes)
        return
    raise ValueError(f"unsupported queue name: {queue_name}")


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
