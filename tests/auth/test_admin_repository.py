import pytest
from unittest.mock import AsyncMock
from src.auth.repositories.admin_repository import AdminRepository

pytestmark = pytest.mark.asyncio


class TestAdminRepository:
    async def test_user_filters_username(self):
        session = AsyncMock()
        repo = AdminRepository(session)
        conds = repo._user_filters(
            username="test", email=None, is_active=None, is_superuser=None, role_id=None
        )
        assert len(conds) == 1

    async def test_user_filters_multiple(self):
        session = AsyncMock()
        repo = AdminRepository(session)
        conds = repo._user_filters(
            username="test",
            email="test@test.com",
            is_active=True,
            is_superuser=None,
            role_id=None,
        )
        assert len(conds) == 3

    async def test_user_filters_all_none(self):
        session = AsyncMock()
        repo = AdminRepository(session)
        conds = repo._user_filters(
            username=None, email=None, is_active=None, is_superuser=None, role_id=None
        )
        assert len(conds) == 0

    async def test_user_filters_role_id(self):
        session = AsyncMock()
        repo = AdminRepository(session)
        conds = repo._user_filters(
            username=None, email=None, is_active=None, is_superuser=None, role_id=1
        )
        assert len(conds) == 1
