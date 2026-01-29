import pytest
from unittest.mock import AsyncMock, MagicMock
from src.auth.services.admin_service import AdminService

pytestmark = pytest.mark.asyncio


class TestAdminService:
    async def test_get_users_paginated(self):
        mock_repo = AsyncMock()
        mock_repo.get_users_paginated.return_value = ([], 0)

        service = AdminService(mock_repo)
        result = await service.get_users(page=1, size=20)

        mock_repo.get_users_paginated.assert_called_once_with(page=1, size=20)
        assert result == ([], 0)

    async def test_create_user_hashes_password(self):
        mock_repo = AsyncMock()
        mock_repo.create_user.return_value = MagicMock(id=1, username="test")

        service = AdminService(mock_repo)

        data = MagicMock()
        data.password = "plain_password"

        def hasher(p):
            return f"hashed_{p}"

        await service.create_user(data, password_hasher=hasher)

        mock_repo.create_user.assert_called_once()
        call_args = mock_repo.create_user.call_args
        assert call_args[0][1] == "hashed_plain_password"
