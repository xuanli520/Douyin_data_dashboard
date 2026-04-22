from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from collections.abc import Sequence
from threading import Event, Thread
from typing import Callable

from src import session
from src.config import get_settings
from src.tasks.collection import douyin_shop_agent, douyin_shop_dashboard
from src.tasks.etl import orders as etl_orders
from src.tasks.etl import products as etl_products

logger = logging.getLogger(__name__)

_MULTIPROCESS_QUEUES = frozenset({"etl_orders", "etl_products"})


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


def _start_runner_thread(queue_name: str, runner: Callable[[], None]) -> Thread:
    thread = Thread(target=runner, name=f"worker-{queue_name}", daemon=True)
    thread.start()
    return thread


def _start_queue(queue_name: str, runner: Callable[[], None]) -> Thread | None:
    if queue_name in _MULTIPROCESS_QUEUES:
        runner()
        return None
    return _start_runner_thread(queue_name, runner)


def _wait_forever(
    stop_event: Event | None = None,
    threads: Sequence[Thread] | Thread | None = None,
) -> None:
    worker_stop_event = stop_event or Event()
    thread_list = (
        list(threads)
        if isinstance(threads, Sequence)
        else ([threads] if threads is not None else [])
    )
    try:
        while not worker_stop_event.wait(5):
            for thread in thread_list:
                if not thread.is_alive():
                    logger.error(
                        "worker thread exited unexpectedly name=%s", thread.name
                    )
                    return
    except KeyboardInterrupt:
        worker_stop_event.set()
    logger.info("Shutting down workers")


def run_all(etl_processes: int = 2, *, stop_event: Event | None = None) -> None:
    threads: list[Thread] = []
    for queue_name, runner in _queue_runners(etl_processes).items():
        thread = _start_queue(queue_name, runner)
        if thread is not None:
            threads.append(thread)

    if stop_event is None:
        _wait_forever(threads=threads)
    else:
        _wait_forever(stop_event, threads)


def run_queue(queue_name: str, etl_processes: int = 2) -> None:
    runner = _queue_runners(etl_processes).get(queue_name)
    if runner is None:
        raise ValueError(f"unsupported queue name: {queue_name}")
    runner()


def _start_worker_loop() -> tuple[asyncio.AbstractEventLoop, Thread]:
    loop = asyncio.new_event_loop()
    ready = Event()

    def _run_loop() -> None:
        asyncio.set_event_loop(loop)
        loop.call_soon(ready.set)
        try:
            loop.run_forever()
        except Exception:
            logger.exception("worker asyncio loop crashed")

    thread = Thread(target=_run_loop, name="worker-asyncio-loop", daemon=True)
    thread.start()
    ready.wait()
    session.bind_worker_loop(loop)
    return loop, thread


def _stop_worker_loop(loop: asyncio.AbstractEventLoop, thread: Thread) -> None:
    session.bind_worker_loop(None)
    try:
        if loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
    except RuntimeError:
        pass
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
    session.run_coro(session.close_db())


def main() -> None:
    args = _parse_args()
    loop, loop_thread = _start_worker_loop()
    stop_event = Event()

    def _handle_signal(signum, _frame):
        logger.info("Received signal %s, shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        _init_worker_db()
        if args.queue:
            runner = _queue_runners(args.etl_processes).get(args.queue)
            if runner is None:
                raise ValueError(f"unsupported queue name: {args.queue}")
            runner_thread = _start_queue(args.queue, runner)
            _wait_forever(stop_event, runner_thread)
        else:
            run_all(etl_processes=args.etl_processes, stop_event=stop_event)
    finally:
        try:
            _close_worker_db()
        finally:
            _stop_worker_loop(loop, loop_thread)


if __name__ == "__main__":
    main()
