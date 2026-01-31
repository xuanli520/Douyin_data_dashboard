from sqlalchemy import select, func, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.models import User, Role, Permission, UserRole, RolePermission
from src.exceptions import BusinessException
from src.shared.errors import ErrorCode


class AdminRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _ensure_roles_exist(self, role_ids: list[int]) -> None:
        if not role_ids:
            return
        rows = await self.session.execute(select(Role.id).where(Role.id.in_(role_ids)))
        found = set(rows.scalars().all())
        missing = [rid for rid in set(role_ids) if rid not in found]
        if missing:
            raise BusinessException(
                ErrorCode.ROLE_NOT_FOUND, f"Role not found: {missing}"
            )

    async def _ensure_permissions_exist(self, permission_ids: list[int]) -> None:
        if not permission_ids:
            return
        rows = await self.session.execute(
            select(Permission.id).where(Permission.id.in_(permission_ids))
        )
        found = set(rows.scalars().all())
        missing = [pid for pid in set(permission_ids) if pid not in found]
        if missing:
            raise BusinessException(
                ErrorCode.PERMISSION_NOT_FOUND, f"Permission not found: {missing}"
            )

    def _user_filters(
        self,
        username: str | None,
        email: str | None,
        is_active: bool | None,
        is_superuser: bool | None,
        role_id: int | None,
    ):
        conds = []
        if username:
            conds.append(User.username.ilike(f"%{username}%"))
        if email:
            conds.append(User.email.ilike(f"%{email}%"))
        if is_active is not None:
            conds.append(User.is_active == is_active)
        if is_superuser is not None:
            conds.append(User.is_superuser == is_superuser)
        if role_id is not None:
            conds.append(
                User.id.in_(select(UserRole.user_id).where(UserRole.role_id == role_id))
            )
        return conds

    async def get_users_paginated(
        self,
        page: int,
        size: int,
        username: str | None = None,
        email: str | None = None,
        is_active: bool | None = None,
        is_superuser: bool | None = None,
        role_id: int | None = None,
    ) -> tuple[list[User], int]:
        conds = self._user_filters(username, email, is_active, is_superuser, role_id)

        stmt = (
            select(User)
            .options(selectinload(User.roles))
            .where(and_(*conds) if conds else True)
            .order_by(User.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )

        count_stmt = select(func.count(User.id)).where(and_(*conds) if conds else True)

        users = (await self.session.execute(stmt)).scalars().all()
        total = (await self.session.execute(count_stmt)).scalar_one()

        return list(users), int(total)

    async def get_user_by_id(self, user_id: int) -> User | None:
        stmt = select(User).options(selectinload(User.roles)).where(User.id == user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create_user(self, data, hashed_password: str) -> User:
        await self._ensure_roles_exist(data.role_ids)

        try:
            async with self.session.begin():
                user = User(
                    username=data.username,
                    email=data.email,
                    hashed_password=hashed_password,
                    gender=data.gender,
                    phone=data.phone,
                    department=data.department,
                )
                self.session.add(user)
                await self.session.flush()

                for rid in set(data.role_ids):
                    self.session.add(UserRole(user_id=user.id, role_id=rid))

            stmt = (
                select(User).options(selectinload(User.roles)).where(User.id == user.id)
            )
            user = (await self.session.execute(stmt)).scalar_one()
            return user

        except IntegrityError as e:
            constraint_name = (
                str(e.orig.diag.constraint_name) if e.orig and e.orig.diag else ""
            )
            if "username" in constraint_name:
                raise BusinessException(
                    ErrorCode.USER_USERNAME_CONFLICT, "Username already exists"
                ) from e
            elif "email" in constraint_name:
                raise BusinessException(
                    ErrorCode.USER_EMAIL_CONFLICT, "Email already exists"
                ) from e
            elif "phone" in constraint_name:
                raise BusinessException(
                    ErrorCode.USER_PHONE_CONFLICT, "Phone already exists"
                ) from e
            raise BusinessException(
                ErrorCode.USER_USERNAME_CONFLICT, "User unique conflict"
            ) from e

    async def update_user(
        self, user_id: int, data, hashed_password: str | None = None
    ) -> User:
        user = await self.get_user_by_id(user_id)
        if not user:
            raise BusinessException(ErrorCode.USER_NOT_FOUND, "User not found")

        if data.role_ids is not None:
            await self._ensure_roles_exist(data.role_ids)

        try:
            in_transaction = self.session.in_transaction()
            if in_transaction:
                if data.username is not None:
                    user.username = data.username
                if data.email is not None:
                    user.email = data.email
                if hashed_password is not None:
                    user.hashed_password = hashed_password
                if data.is_active is not None:
                    user.is_active = data.is_active
                if data.is_superuser is not None:
                    user.is_superuser = data.is_superuser
                if data.is_verified is not None:
                    user.is_verified = data.is_verified
                if data.gender is not None:
                    user.gender = data.gender
                if data.phone is not None:
                    user.phone = data.phone
                if data.department is not None:
                    user.department = data.department

                if data.role_ids is not None:
                    await self.session.execute(
                        UserRole.__table__.delete().where(UserRole.user_id == user_id)
                    )
                    for rid in set(data.role_ids):
                        self.session.add(UserRole(user_id=user_id, role_id=rid))
            else:
                async with self.session.begin():
                    if data.username is not None:
                        user.username = data.username
                    if data.email is not None:
                        user.email = data.email
                    if hashed_password is not None:
                        user.hashed_password = hashed_password
                    if data.is_active is not None:
                        user.is_active = data.is_active
                    if data.is_superuser is not None:
                        user.is_superuser = data.is_superuser
                    if data.is_verified is not None:
                        user.is_verified = data.is_verified
                    if data.gender is not None:
                        user.gender = data.gender
                    if data.phone is not None:
                        user.phone = data.phone
                    if data.department is not None:
                        user.department = data.department

                    if data.role_ids is not None:
                        await self.session.execute(
                            UserRole.__table__.delete().where(
                                UserRole.user_id == user_id
                            )
                        )
                        for rid in set(data.role_ids):
                            self.session.add(UserRole(user_id=user_id, role_id=rid))

            stmt = (
                select(User).options(selectinload(User.roles)).where(User.id == user_id)
            )
            user = (await self.session.execute(stmt)).scalar_one()
            return user
        except IntegrityError as e:
            await self.session.rollback()
            constraint_name = (
                str(e.orig.diag.constraint_name) if e.orig and e.orig.diag else ""
            )
            if "username" in constraint_name:
                raise BusinessException(
                    ErrorCode.USER_USERNAME_CONFLICT, "Username already exists"
                ) from e
            elif "email" in constraint_name:
                raise BusinessException(
                    ErrorCode.USER_EMAIL_CONFLICT, "Email already exists"
                ) from e
            elif "phone" in constraint_name:
                raise BusinessException(
                    ErrorCode.USER_PHONE_CONFLICT, "Phone already exists"
                ) from e
            raise BusinessException(
                ErrorCode.USER_USERNAME_CONFLICT, "User unique conflict"
            ) from e

    async def delete_user(self, user_id: int) -> None:
        user = await self.get_user_by_id(user_id)
        if not user:
            raise BusinessException(ErrorCode.USER_NOT_FOUND, "User not found")

        if self.session.in_transaction():
            await self.session.execute(
                UserRole.__table__.delete().where(UserRole.user_id == user_id)
            )
            await self.session.delete(user)
        else:
            async with self.session.begin():
                await self.session.execute(
                    UserRole.__table__.delete().where(UserRole.user_id == user_id)
                )
                await self.session.delete(user)

    async def assign_user_roles(self, user_id: int, role_ids: list[int]) -> None:
        async with self.session.begin():
            user = await self.get_user_by_id(user_id)
            if not user:
                raise BusinessException(ErrorCode.USER_NOT_FOUND, "User not found")
            await self._ensure_roles_exist(role_ids)

            await self.session.execute(
                UserRole.__table__.delete().where(UserRole.user_id == user_id)
            )
            for rid in set(role_ids):
                self.session.add(UserRole(user_id=user_id, role_id=rid))

    async def get_roles(self) -> list[Role]:
        stmt = select(Role).order_by(Role.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_role_by_id(self, role_id: int) -> Role | None:
        stmt = (
            select(Role)
            .options(selectinload(Role.permissions))
            .where(Role.id == role_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create_role(self, data) -> Role:
        try:
            async with self.session.begin():
                role = Role(name=data.name, description=data.description)
                self.session.add(role)
            await self.session.refresh(role)
            return role
        except IntegrityError as e:
            raise BusinessException(
                ErrorCode.ROLE_NAME_CONFLICT, "Role name already exists"
            ) from e

    async def update_role(self, role_id: int, data) -> Role:
        try:
            async with self.session.begin():
                role = await self.get_role_by_id(role_id)
                if not role:
                    raise BusinessException(ErrorCode.ROLE_NOT_FOUND, "Role not found")
                if role.is_system:
                    raise BusinessException(
                        ErrorCode.ROLE_CANNOT_MODIFY_SYSTEM,
                        "Cannot modify system role",
                    )

                if data.name is not None:
                    role.name = data.name
                if data.description is not None:
                    role.description = data.description
            await self.session.refresh(role)
            return role
        except IntegrityError as e:
            raise BusinessException(
                ErrorCode.ROLE_NAME_CONFLICT, "Role name already exists"
            ) from e

    async def delete_role(self, role_id: int) -> None:
        async with self.session.begin():
            role = await self.get_role_by_id(role_id)
            if not role:
                raise BusinessException(ErrorCode.ROLE_NOT_FOUND, "Role not found")
            if role.is_system:
                raise BusinessException(
                    ErrorCode.ROLE_CANNOT_DELETE_SYSTEM, "Cannot delete system role"
                )

            role.permissions = []
            await self.session.execute(
                UserRole.__table__.delete().where(UserRole.role_id == role_id)
            )
            await self.session.delete(role)

    async def assign_permissions(self, role_id: int, permission_ids: list[int]) -> None:
        permission_ids = list(set(permission_ids))
        async with self.session.begin():
            role = await self.get_role_by_id(role_id)
            if not role:
                raise BusinessException(ErrorCode.ROLE_NOT_FOUND, "Role not found")
            if role.is_system:
                raise BusinessException(
                    ErrorCode.ROLE_CANNOT_MODIFY_SYSTEM, "Cannot modify system role"
                )

            await self._ensure_permissions_exist(permission_ids)
            await self.session.execute(
                RolePermission.__table__.delete().where(
                    RolePermission.role_id == role_id
                )
            )
            for pid in permission_ids:
                self.session.add(RolePermission(role_id=role_id, permission_id=pid))

    async def get_permissions(self) -> list[Permission]:
        stmt = select(Permission).order_by(Permission.module, Permission.code)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_user_stats(self) -> dict:
        total = (await self.session.execute(select(func.count(User.id)))).scalar_one()
        active = (
            await self.session.execute(
                select(func.count(User.id)).where(User.is_active)
            )
        ).scalar_one()
        inactive = (
            await self.session.execute(
                select(func.count(User.id)).where(not User.is_active)
            )
        ).scalar_one()
        superusers = (
            await self.session.execute(
                select(func.count(User.id)).where(User.is_superuser)
            )
        ).scalar_one()
        return {
            "total": int(total),
            "active": int(active),
            "inactive": int(inactive),
            "superusers": int(superusers),
        }
