from collections.abc import Callable
from typing import Any, TypeVar

from sqlalchemy.exc import (
    DataError,
    IntegrityError,
    InvalidRequestError,
    OperationalError,
    PendingRollbackError,
)
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class _Unset:
    """Sentinel value to distinguish between None and unset."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return "UNSET"


UNSET = _Unset()


class TransactionError(Exception):
    pass


class BaseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _tx(
        self,
        operation: Callable[[], Any],
    ) -> Any:
        if self.session.in_transaction():
            return await operation()

        try:
            async with self.session.begin():
                return await operation()
        except (
            DataError,
            IntegrityError,
            PendingRollbackError,
            InvalidRequestError,
            OperationalError,
        ):
            await self.session.rollback()
            raise

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
        constraint_mapping: dict[str, str],
        default_error: tuple[str, str],
    ) -> None:
        from src.exceptions import BusinessException
        from src.shared.errors import ErrorCode

        constraint_name = (
            str(error.orig.diag.constraint_name)
            if error.orig and error.orig.diag
            else ""
        )
        for key, message in constraint_mapping.items():
            if key in constraint_name:
                raise BusinessException(ErrorCode(message), message) from error

        raise BusinessException(
            ErrorCode(default_error[0]), default_error[1]
        ) from error
