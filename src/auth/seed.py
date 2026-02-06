"""Initial permission data"""

from sqlalchemy import select
from src.session import async_session_factory
from src.auth.models import Permission, Role, RolePermission

PERMISSIONS = [
    ("user:read", "查看用户", "user", "查看用户列表和详情"),
    ("user:create", "创建用户", "user", "创建新用户"),
    ("user:update", "更新用户", "user", "更新用户信息"),
    ("user:delete", "删除用户", "user", "删除用户"),
    ("user:manage_roles", "管理用户角色", "user", "分配/移除用户角色"),
    ("role:read", "查看角色", "role", "查看角色列表和详情"),
    ("role:create", "创建角色", "role", "创建新角色"),
    ("role:update", "更新角色", "role", "更新角色信息"),
    ("role:delete", "删除角色", "role", "删除角色"),
    ("role:manage_permissions", "管理角色权限", "role", "分配/移除角色权限"),
    ("permission:read", "查看权限", "permission", "查看权限列表"),
    ("system:settings", "系统设置", "system", "系统设置"),
    ("system:logs", "查看日志", "system", "查看系统日志"),
    ("data_source:view", "查看数据源", "data_source", "查看数据源列表和详情"),
    ("data_source:create", "创建数据源", "data_source", "创建新数据源"),
    ("data_source:update", "更新数据源", "data_source", "更新数据源信息"),
    ("data_source:delete", "删除数据源", "data_source", "删除数据源"),
    ("data_import:view", "查看导入历史", "data_import", "查看数据导入记录"),
    ("data_import:upload", "上传文件", "data_import", "上传数据文件"),
    ("data_import:parse", "解析文件", "data_import", "解析上传的文件"),
    ("data_import:validate", "验证数据", "data_import", "验证导入数据"),
    ("data_import:confirm", "确认导入", "data_import", "确认并执行数据导入"),
    ("data_import:cancel", "取消导入", "data_import", "取消数据导入操作"),
    ("task:view", "查看任务", "task", "查看任务列表和执行记录"),
    ("task:create", "创建任务", "task", "创建新任务"),
    ("task:execute", "执行任务", "task", "手动触发任务执行"),
    ("task:cancel", "取消任务", "task", "取消任务执行"),
]


async def seed_permissions():
    """Initialize permission data (idempotent)"""
    async with async_session_factory() as session:
        for code, name, module, description in PERMISSIONS:
            existing = await session.execute(
                select(Permission).where(Permission.code == code)
            )
            if not existing.scalar_one_or_none():
                session.add(
                    Permission(
                        code=code,
                        name=name,
                        module=module,
                        description=description,
                    )
                )
        await session.commit()


async def seed_admin_role_permissions():
    """Assign all permissions to admin role"""
    async with async_session_factory() as session:
        result = await session.execute(select(Role).where(Role.name == "admin"))
        admin_role = result.scalar_one_or_none()
        if not admin_role:
            return

        perms = await session.execute(select(Permission))
        perms = perms.scalars().all()

        for perm in perms:
            exist = await session.execute(
                select(RolePermission).where(
                    RolePermission.role_id == admin_role.id,
                    RolePermission.permission_id == perm.id,
                )
            )
            if not exist.scalar_one_or_none():
                session.add(
                    RolePermission(role_id=admin_role.id, permission_id=perm.id)
                )
        await session.commit()
