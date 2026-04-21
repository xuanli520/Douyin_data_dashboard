import ast
import asyncio
import importlib
import logging
import threading
from collections.abc import AsyncGenerator, Coroutine
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

T = TypeVar("T")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _DbState:
    engine: AsyncEngine
    session_factory: sessionmaker[AsyncSession]


_db_state: _DbState | None = None
_worker_loop: asyncio.AbstractEventLoop | None = None
_db_state_lock = threading.Lock()
_worker_loop_lock = threading.Lock()


def _get_db_state() -> _DbState | None:
    with _db_state_lock:
        return _db_state


def _get_engine_options(url: str, echo: bool) -> dict[str, Any]:
    options: dict[str, Any] = {"echo": echo}
    try:
        if make_url(url).get_backend_name() == "sqlite":
            return options
        from src.config import get_settings

        db_settings = get_settings().db
    except Exception as exc:
        logger.warning("Failed to load database pool settings, using defaults: %s", exc)
        return options

    options.update(
        pool_size=db_settings.pool_size,
        max_overflow=db_settings.max_overflow,
        pool_recycle=db_settings.pool_recycle,
    )
    return options


def _get_run_coro_timeout_seconds() -> float:
    try:
        from src.config import get_settings

        timeout_seconds = float(get_settings().db.run_coro_timeout_seconds)
    except Exception as exc:
        logger.warning(
            "Failed to load run_coro timeout setting, using default: %s", exc
        )
        return 30.0
    return timeout_seconds if timeout_seconds > 0 else 30.0


def __getattr__(name: str) -> Any:
    state = _get_db_state()
    if name == "engine":
        return None if state is None else state.engine
    if name == "async_session_factory":
        return None if state is None else state.session_factory
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _module_contains_sqlmodel_table(module_path: Path) -> bool:
    try:
        tree = ast.parse(
            module_path.read_text(encoding="utf-8"),
            filename=str(module_path),
        )
    except (SyntaxError, UnicodeDecodeError):
        return False
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for keyword in node.keywords:
            if keyword.arg != "table":
                continue
            if isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                return True
    return False


@lru_cache(maxsize=1)
def _discover_sqlmodel_model_modules() -> tuple[str, ...]:
    src_root = Path(__file__).resolve().parent
    modules: list[str] = []
    for module_path in src_root.rglob("*.py"):
        if module_path.name == "__init__.py":
            continue
        if "__pycache__" in module_path.parts:
            continue
        if not _module_contains_sqlmodel_table(module_path):
            continue
        relative_path = module_path.relative_to(src_root.parent).with_suffix("")
        modules.append(".".join(relative_path.parts))
    return tuple(sorted(modules))


def _load_sqlmodel_models() -> None:
    for module_name in _discover_sqlmodel_model_modules():
        importlib.import_module(module_name)


async def init_db(url: str, echo: bool = False) -> None:
    global _db_state
    _load_sqlmodel_models()
    with _db_state_lock:
        if _db_state is not None:
            return

    next_engine = create_async_engine(url, **_get_engine_options(url, echo))
    try:
        if next_engine.dialect.name == "sqlite":

            @event.listens_for(next_engine.sync_engine, "connect")
            def set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        next_factory = sessionmaker(
            next_engine, class_=AsyncSession, expire_on_commit=False
        )
    except Exception:
        await next_engine.dispose()
        raise

    dispose_engine = False
    with _db_state_lock:
        if _db_state is None:
            _db_state = _DbState(engine=next_engine, session_factory=next_factory)
            return
        dispose_engine = True
    if dispose_engine:
        await next_engine.dispose()


async def close_db() -> None:
    global _db_state
    old_state: _DbState | None = None
    with _db_state_lock:
        old_state = _db_state
        _db_state = None
    if old_state is None:
        return
    await old_state.engine.dispose()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    state = _get_db_state()
    if state is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with state.session_factory() as session:
        try:
            yield session
            if session.in_transaction():
                await session.commit()
        except Exception:
            if session.in_transaction():
                await session.rollback()
            raise


def bind_worker_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    global _worker_loop
    with _worker_loop_lock:
        _worker_loop = loop


def run_coro(coro: Coroutine[Any, Any, T]) -> T:
    with _worker_loop_lock:
        loop = _worker_loop

    if loop is None or loop.is_closed():
        try:
            return asyncio.run(coro)
        except RuntimeError:
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()

    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=_get_run_coro_timeout_seconds())
    except TimeoutError:
        future.cancel()
        raise
