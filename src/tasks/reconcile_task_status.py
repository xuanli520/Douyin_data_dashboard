from __future__ import annotations

from src import session
from src.config import get_settings
from src.tasks.status_recovery import recover_stale_running_task_executions


def main() -> None:
    settings = get_settings()
    session.run_coro(session.init_db(settings.db.url, settings.db.echo))
    try:
        recover_stale_running_task_executions()
    finally:
        session.run_coro(session.close_db())


if __name__ == "__main__":
    main()
