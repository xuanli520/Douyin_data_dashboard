"""add data_source and data_import permissions

Revision ID: 8e9cd22532a3
Revises: d1234567890ab
Create Date: 2026-02-07 22:06:14.343300

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8e9cd22532a3"
down_revision: Union[str, Sequence[str], None] = "d1234567890ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    permissions = [
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

    for code, name, module, description in permissions:
        conn.execute(
            sa.text(
                """
            INSERT INTO permissions (code, name, description, module, created_at, updated_at)
            VALUES (:code, :name, :description, :module, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (code) DO NOTHING
            """
            ),
            {"code": code, "name": name, "description": description, "module": module},
        )

    for code, name, module, description in permissions:
        conn.execute(
            sa.text(
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


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()

    permission_codes = [
        "data_source:view",
        "data_source:create",
        "data_source:update",
        "data_source:delete",
        "data_import:view",
        "data_import:upload",
        "data_import:parse",
        "data_import:validate",
        "data_import:confirm",
        "data_import:cancel",
        "task:view",
        "task:create",
        "task:execute",
        "task:cancel",
    ]

    for code in permission_codes:
        conn.execute(
            sa.text(
                """
            DELETE FROM role_permissions
            WHERE permission_id IN (SELECT id FROM permissions WHERE code = :code)
            """
            ),
            {"code": code},
        )
        conn.execute(
            sa.text("DELETE FROM permissions WHERE code = :code"),
            {"code": code},
        )
    conn.commit()
