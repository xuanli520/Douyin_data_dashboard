import asyncio
from collections.abc import AsyncGenerator, Coroutine
from typing import Any, TypeVar

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

engine: AsyncEngine | None = None
async_session_factory: sessionmaker[AsyncSession] | None = None
_worker_loop: asyncio.AbstractEventLoop | None = None
T = TypeVar("T")


async def init_db(url: str, echo: bool = False) -> None:
    global engine, async_session_factory
    if engine is not None:
        await engine.dispose()
    engine = create_async_engine(url, echo=echo)

    if "sqlite" in url:

        @event.listens_for(engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )


async def close_db() -> None:
    global engine, async_session_factory
    if engine is None:
        async_session_factory = None
        return
    await engine.dispose()
    engine = None
    async_session_factory = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
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
    _worker_loop = loop


def run_coro(coro: Coroutine[Any, Any, T]) -> T:
    loop = _worker_loop
    if loop is None or loop.is_closed():
        return asyncio.run(coro)
    return asyncio.run_coroutine_threadsafe(coro, loop).result()
