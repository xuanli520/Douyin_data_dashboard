import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from src.auth.services.admin_service import AdminService

pytestmark = pytest.mark.asyncio


def create_mock_user():
    now = datetime.now(timezone.utc)
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.username = "test"
    mock_user.email = "test@test.com"
    mock_user.is_active = True
    mock_user.is_superuser = False
    mock_user.is_verified = False
    mock_user.gender = None
    mock_user.phone = None
    mock_user.department = None
    mock_user.created_at = now
    mock_user.updated_at = now
    mock_user.roles = []
    return mock_user


class TestAdminService:
    async def test_get_users_paginated(self):
        mock_repo = AsyncMock()
        mock_repo.get_users_paginated.return_value = ([create_mock_user()], 1)

        service = AdminService(mock_repo)
        result = await service.get_users(page=1, size=20)

        mock_repo.get_users_paginated.assert_called_once_with(page=1, size=20)
        assert result[1] == 1
        assert len(result[0]) == 1

    async def test_create_user_hashes_password(self):
        mock_repo = AsyncMock()
        mock_repo.create_user.return_value = create_mock_user()

        service = AdminService(mock_repo)

        data = MagicMock()
        data.password = "plain_password"

        def hasher(p):
            return f"hashed_{p}"

        await service.create_user(data, password_hasher=hasher)

        mock_repo.create_user.assert_called_once()
        call_args = mock_repo.create_user.call_args
        assert call_args[0][1] == "hashed_plain_password"
