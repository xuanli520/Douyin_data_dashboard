from fastapi import APIRouter, Depends, Query

from src.auth import current_user, require_permissions, User
from src.auth.services.admin_service import AdminService, get_admin_service
from src.auth.schemas import (
    UserListItem,
    UserCreateByAdmin,
    UserUpdateByAdmin,
    AssignRolesRequest,
    RoleRead,
    RoleCreate,
    RoleUpdate,
    RoleWithPermissions,
    PermissionRead,
    PermissionAssign,
    UserStatsResponse,
)
from src.exceptions import BusinessException
from src.shared.errors import ErrorCode
from src.shared.schemas import PaginatedData
from src.audit import AuditService, get_audit_service
from src.audit.schemas import AuditAction, AuditResult

router = APIRouter(prefix="/admin", tags=["admin"])

can_user_read = require_permissions("user:read", bypass_superuser=True)
can_user_create = require_permissions("user:create", bypass_superuser=True)
can_user_update = require_permissions("user:update", bypass_superuser=True)
can_user_delete = require_permissions("user:delete", bypass_superuser=True)
can_user_manage_roles = require_permissions("user:manage_roles", bypass_superuser=True)

can_role_read = require_permissions("role:read", bypass_superuser=True)
can_role_create = require_permissions("role:create", bypass_superuser=True)
can_role_update = require_permissions("role:update", bypass_superuser=True)
can_role_delete = require_permissions("role:delete", bypass_superuser=True)
can_role_manage_permissions = require_permissions(
    "role:manage_permissions", bypass_superuser=True
)

can_permission_read = require_permissions("permission:read", bypass_superuser=True)


@router.get(
    "/users",
    response_model=PaginatedData[UserListItem],
    dependencies=[Depends(can_user_read)],
)
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    username: str | None = Query(None, max_length=50),
    email: str | None = Query(None, max_length=320),
    is_active: bool | None = Query(None),
    is_superuser: bool | None = Query(None),
    role_id: int | None = Query(None),
    admin_service: AdminService = Depends(get_admin_service),
):
    users, total = await admin_service.get_users(
        page=page,
        size=size,
        username=username,
        email=email,
        is_active=is_active,
        is_superuser=is_superuser,
        role_id=role_id,
    )
    return PaginatedData.create(items=users, total=total, page=page, size=size)


@router.get(
    "/users/stats",
    response_model=UserStatsResponse,
    dependencies=[Depends(can_user_read)],
)
async def get_user_stats(admin_service: AdminService = Depends(get_admin_service)):
    stats = await admin_service.get_user_stats()
    return UserStatsResponse(**stats)


@router.get(
    "/users/{user_id}",
    response_model=UserListItem,
    dependencies=[Depends(can_user_read)],
)
async def get_user(
    user_id: int, admin_service: AdminService = Depends(get_admin_service)
):
    return await admin_service.get_user_detail(user_id)


@router.post(
    "/users", response_model=UserListItem, dependencies=[Depends(can_user_create)]
)
async def create_user(
    data: UserCreateByAdmin,
    admin_service: AdminService = Depends(get_admin_service),
    audit_service: AuditService = Depends(get_audit_service),
    current_user: User = Depends(current_user),
):
    from src.auth.backend import get_password_hash

    user = await admin_service.create_user(data, password_hasher=get_password_hash)

    await audit_service.log(
        action=AuditAction.CREATE,
        result=AuditResult.SUCCESS,
        actor_id=current_user.id,
        resource_type="user",
        resource_id=str(user.id),
        extra={"username": user.username, "email": user.email},
    )
    return user


@router.patch(
    "/users/{user_id}",
    response_model=UserListItem,
    dependencies=[Depends(can_user_update)],
)
async def update_user(
    user_id: int,
    data: UserUpdateByAdmin,
    admin_service: AdminService = Depends(get_admin_service),
    audit_service: AuditService = Depends(get_audit_service),
    current_user: User = Depends(current_user),
):
    from src.auth.backend import get_password_hash

    user = await admin_service.update_user(
        user_id, data, password_hasher=get_password_hash
    )

    updated_fields = data.model_dump(exclude_defaults=True, exclude={"password"})
    await audit_service.log(
        action=AuditAction.UPDATE,
        result=AuditResult.SUCCESS,
        actor_id=current_user.id,
        resource_type="user",
        resource_id=str(user_id),
        extra={"updated_fields": updated_fields},
    )
    return user


@router.delete("/users/{user_id}", dependencies=[Depends(can_user_delete)])
async def delete_user(
    user_id: int,
    admin_service: AdminService = Depends(get_admin_service),
    audit_service: AuditService = Depends(get_audit_service),
    current_user: User = Depends(current_user),
):
    if user_id == current_user.id:
        raise BusinessException(
            ErrorCode.USER_CANNOT_DELETE_SELF, "Cannot delete yourself"
        )

    await admin_service.delete_user(user_id)

    await audit_service.log(
        action=AuditAction.DELETE,
        result=AuditResult.SUCCESS,
        actor_id=current_user.id,
        resource_type="user",
        resource_id=str(user_id),
    )
    return {"detail": "User deleted successfully"}


@router.post("/users/{user_id}/roles", dependencies=[Depends(can_user_manage_roles)])
async def assign_user_roles(
    user_id: int,
    data: AssignRolesRequest,
    admin_service: AdminService = Depends(get_admin_service),
    audit_service: AuditService = Depends(get_audit_service),
    current_user: User = Depends(current_user),
):
    await admin_service.assign_user_roles(user_id, data.role_ids)

    await audit_service.log(
        action=AuditAction.UPDATE,
        result=AuditResult.SUCCESS,
        actor_id=current_user.id,
        resource_type="user_roles",
        resource_id=str(user_id),
        extra={"role_ids": data.role_ids},
    )
    return {"detail": "Roles assigned successfully"}


@router.get(
    "/roles", response_model=list[RoleRead], dependencies=[Depends(can_role_read)]
)
async def list_roles(admin_service: AdminService = Depends(get_admin_service)):
    roles = await admin_service.get_roles()
    return roles


@router.get(
    "/roles/{role_id}",
    response_model=RoleWithPermissions,
    dependencies=[Depends(can_role_read)],
)
async def get_role(
    role_id: int, admin_service: AdminService = Depends(get_admin_service)
):
    role = await admin_service.get_role_detail(role_id)
    if not role:
        raise BusinessException(ErrorCode.ROLE_NOT_FOUND, "Role not found")
    return role


@router.post("/roles", response_model=RoleRead, dependencies=[Depends(can_role_create)])
async def create_role(
    data: RoleCreate,
    admin_service: AdminService = Depends(get_admin_service),
    audit_service: AuditService = Depends(get_audit_service),
    current_user: User = Depends(current_user),
):
    role = await admin_service.create_role(data)
    await audit_service.log(
        action=AuditAction.CREATE,
        result=AuditResult.SUCCESS,
        actor_id=current_user.id,
        resource_type="role",
        resource_id=str(role.id),
        extra={"role_name": role.name},
    )
    return role


@router.patch(
    "/roles/{role_id}", response_model=RoleRead, dependencies=[Depends(can_role_update)]
)
async def update_role(
    role_id: int,
    data: RoleUpdate,
    admin_service: AdminService = Depends(get_admin_service),
    audit_service: AuditService = Depends(get_audit_service),
    current_user: User = Depends(current_user),
):
    role = await admin_service.update_role(role_id, data)
    await audit_service.log(
        action=AuditAction.UPDATE,
        result=AuditResult.SUCCESS,
        actor_id=current_user.id,
        resource_type="role",
        resource_id=str(role_id),
        extra={"updated_fields": data.model_dump(exclude_defaults=True)},
    )
    return role


@router.delete("/roles/{role_id}", dependencies=[Depends(can_role_delete)])
async def delete_role(
    role_id: int,
    admin_service: AdminService = Depends(get_admin_service),
    audit_service: AuditService = Depends(get_audit_service),
    current_user: User = Depends(current_user),
):
    await admin_service.delete_role(role_id)
    await audit_service.log(
        action=AuditAction.DELETE,
        result=AuditResult.SUCCESS,
        actor_id=current_user.id,
        resource_type="role",
        resource_id=str(role_id),
    )
    return {"detail": "Role deleted successfully"}


@router.post(
    "/roles/{role_id}/permissions", dependencies=[Depends(can_role_manage_permissions)]
)
async def assign_role_permissions(
    role_id: int,
    data: PermissionAssign,
    admin_service: AdminService = Depends(get_admin_service),
    audit_service: AuditService = Depends(get_audit_service),
    current_user: User = Depends(current_user),
):
    await admin_service.assign_role_permissions(role_id, data.permission_ids)

    await audit_service.log(
        action=AuditAction.UPDATE,
        result=AuditResult.SUCCESS,
        actor_id=current_user.id,
        resource_type="role_permissions",
        resource_id=str(role_id),
        extra={"permission_ids": data.permission_ids},
    )
    return {"detail": "Permissions assigned successfully"}


@router.get(
    "/permissions",
    response_model=list[PermissionRead],
    dependencies=[Depends(can_permission_read)],
)
async def list_permissions(admin_service: AdminService = Depends(get_admin_service)):
    return await admin_service.get_permissions()
