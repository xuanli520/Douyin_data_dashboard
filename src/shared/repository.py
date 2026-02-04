from collections.abc import Callable
from typing import Awaitable, TypeVar

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class TransactionError(Exception):
    pass


class BaseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _tx(
        self,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        try:
            if self.session.in_transaction():
                result = await operation()
                await self.session.flush()
                return result
            async with self.session.begin():
                return await operation()
        except IntegrityError as e:
            await self.session.rollback()
            return await self._handle_integrity_error(e)

    async def _add(self, instance: T) -> T:
        async def _do_add():
            self.session.add(instance)
            return instance

        return await self._tx(_do_add)

    async def _flush(self) -> None:
        if self.session.in_transaction():
            await self.session.flush()
        else:
            async with self.session.begin():
                await self.session.flush()

    async def _delete(self, instance: T) -> None:
        async def _do_delete():
            await self.session.delete(instance)

        await self._tx(_do_delete)

    async def _handle_integrity_error(
        self,
        error: IntegrityError,
        constraint_mapping: dict[str, str] | None = None,
        default_error: tuple[str, str] | None = None,
    ) -> None:
        raise error
