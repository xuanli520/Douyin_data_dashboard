from __future__ import annotations

import argparse
import asyncio
import time
from threading import Event, Thread
from typing import Callable

from src import session
from src.config import get_settings
from src.tasks.collection import douyin_shop_agent, douyin_shop_dashboard
from src.tasks.etl import orders as etl_orders
from src.tasks.etl import products as etl_products

_NON_BLOCKING_CONSUME_QUEUES = {
    "collection_shop_dashboard",
    "collection_shop_dashboard_agent",
    "collection_shop_dashboard_dlx",
    "collection_shop_dashboard_agent_dlx",
    "etl_orders_dlx",
    "etl_products_dlx",
}


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


def _wait_forever() -> None:
    while True:
        time.sleep(3600)


def _start_worker_loop() -> tuple[asyncio.AbstractEventLoop, Thread]:
    loop = asyncio.new_event_loop()
    ready = Event()

    def _run_loop() -> None:
        asyncio.set_event_loop(loop)
        ready.set()
        loop.run_forever()

    thread = Thread(target=_run_loop, name="worker-asyncio-loop", daemon=True)
    thread.start()
    ready.wait()
    session.bind_worker_loop(loop)
    return loop, thread


def _stop_worker_loop(loop: asyncio.AbstractEventLoop, thread: Thread) -> None:
    session.bind_worker_loop(None)
    if loop.is_running():
        loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=5)
    if not loop.is_closed():
        loop.close()


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


def _init_worker_db() -> None:
    settings = get_settings()
    session.run_coro(session.init_db(settings.db.url, settings.db.echo))


def _close_worker_db() -> None:
    if session.engine is None:
        return
    session.run_coro(session.close_db())


def main() -> None:
    args = _parse_args()
    loop, loop_thread = _start_worker_loop()
    try:
        _init_worker_db()
        if args.queue:
            run_queue(args.queue, etl_processes=args.etl_processes)
            if args.queue in _NON_BLOCKING_CONSUME_QUEUES:
                _wait_forever()
            return
        run_all(etl_processes=args.etl_processes)
    finally:
        try:
            _close_worker_db()
        finally:
            _stop_worker_loop(loop, loop_thread)


if __name__ == "__main__":
    main()
