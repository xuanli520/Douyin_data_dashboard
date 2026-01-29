from collections.abc import AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.session import get_session
from src.auth.repositories.admin_repository import AdminRepository
from src.auth.schemas import (
    UserListItem,
    RoleRead,
    RoleWithPermissions,
    PermissionRead,
)


class AdminService:
    def __init__(self, repo: AdminRepository):
        self.repo = repo

    async def get_users(self, **kwargs):
        users, total = await self.repo.get_users_paginated(**kwargs)
        return [UserListItem.model_validate(user) for user in users], total

    async def get_user_detail(self, user_id: int):
        user = await self.repo.get_user_by_id(user_id)
        if not user:
            from src.exceptions import BusinessException
            from src.shared.errors import ErrorCode

            raise BusinessException(ErrorCode.USER_NOT_FOUND, "User not found")
        return UserListItem.model_validate(user)

    async def create_user(self, data, password_hasher):
        hashed = password_hasher(data.password)
        user = await self.repo.create_user(data, hashed)
        return UserListItem.model_validate(user)

    async def update_user(self, user_id: int, data, password_hasher):
        hashed = password_hasher(data.password) if data.password else None
        user = await self.repo.update_user(user_id, data, hashed)
        return UserListItem.model_validate(user)

    async def delete_user(self, user_id: int):
        await self.repo.delete_user(user_id)

    async def assign_user_roles(self, user_id: int, role_ids: list[int]):
        await self.repo.assign_user_roles(user_id, role_ids)

    async def get_roles(self):
        roles = await self.repo.get_roles()
        return [RoleRead.model_validate(role) for role in roles]

    async def get_role_detail(self, role_id: int):
        role = await self.repo.get_role_by_id(role_id)
        if not role:
            return None
        return RoleWithPermissions.model_validate(role)

    async def create_role(self, data):
        role = await self.repo.create_role(data)
        return RoleRead.model_validate(role)

    async def update_role(self, role_id: int, data):
        role = await self.repo.update_role(role_id, data)
        return RoleRead.model_validate(role)

    async def delete_role(self, role_id: int):
        await self.repo.delete_role(role_id)

    async def get_permissions(self):
        permissions = await self.repo.get_permissions()
        return [PermissionRead.model_validate(perm) for perm in permissions]

    async def assign_role_permissions(self, role_id: int, permission_ids: list[int]):
        await self.repo.assign_permissions(role_id, permission_ids)

    async def get_user_stats(self):
        return await self.repo.get_user_stats()


async def get_admin_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[AdminService, None]:
    repo = AdminRepository(session=session)
    yield AdminService(repo=repo)
