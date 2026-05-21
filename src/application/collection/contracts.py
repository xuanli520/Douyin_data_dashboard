from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

class SessionFactory(Protocol):
    def __call__(self) -> AbstractAsyncContextManager[AsyncSession]: ...
