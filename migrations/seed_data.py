from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncConnection


def insert_rbac_seed_data_sync(conn: Connection) -> None:
    conn.execute(
        text(
            """
            INSERT INTO roles (name, description, is_system, created_at, updated_at)
            VALUES
                ('admin', 'System administrator role', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                ('user', 'Default user role', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (name) DO NOTHING
            """
        )
    )
    conn.commit()

    permissions = [
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
    ]
    for code, name, module, description in permissions:
        conn.execute(
            text(
                """
                INSERT INTO permissions (code, name, description, module, created_at, updated_at)
                VALUES (:code, :name, :description, :module, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (code) DO NOTHING
                """
            ),
            {"code": code, "name": name, "description": description, "module": module},
        )
    conn.commit()

    for code, name, module, description in permissions:
        conn.execute(
            text(
                """
                INSERT INTO role_permissions (role_id, permission_id, assigned_at)
                SELECT r.id, p.id, CURRENT_TIMESTAMP FROM roles r, permissions p
                WHERE r.name = 'admin' AND p.code = :code
                ON CONFLICT (role_id, permission_id) DO NOTHING
                """
            ),
            {"code": code},
        )
    conn.commit()


async def insert_rbac_seed_data_async(conn: AsyncConnection) -> None:
    await conn.execute(
        text(
            """
            INSERT INTO roles (name, description, is_system, created_at, updated_at)
            VALUES
                ('admin', 'System administrator role', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                ('user', 'Default user role', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (name) DO NOTHING
            """
        )
    )
    await conn.commit()

    permissions = [
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
    ]
    for code, name, module, description in permissions:
        await conn.execute(
            text(
                """
                INSERT INTO permissions (code, name, description, module, created_at, updated_at)
                VALUES (:code, :name, :description, :module, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (code) DO NOTHING
                """
            ),
            {"code": code, "name": name, "description": description, "module": module},
        )
    await conn.commit()

    for code, name, module, description in permissions:
        await conn.execute(
            text(
                """
                INSERT INTO role_permissions (role_id, permission_id, assigned_at)
                SELECT r.id, p.id, CURRENT_TIMESTAMP FROM roles r, permissions p
                WHERE r.name = 'admin' AND p.code = :code
                ON CONFLICT (role_id, permission_id) DO NOTHING
                """
            ),
            {"code": code},
        )
    await conn.commit()
