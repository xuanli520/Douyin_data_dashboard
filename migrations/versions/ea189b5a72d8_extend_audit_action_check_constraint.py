"""extend audit action check constraint

Revision ID: ea189b5a72d8
Revises: 06038dbc9807
Create Date: 2026-02-15 10:30:44.860167

"""

from typing import Sequence, Union

from alembic import op


revision: str = "ea189b5a72d8"
down_revision: Union[str, Sequence[str], None] = "06038dbc9807"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUDIT_ACTIONS = [
    "login",
    "logout",
    "refresh",
    "register",
    "verify_email",
    "forgot_password",
    "reset_password",
    "permission_check",
    "role_check",
    "protected_resource_access",
    "create",
    "update",
    "delete",
    "data_source_bind",
    "data_source_unbind",
    "data_source_update",
    "data_source_sync",
    "task_create",
    "task_update",
    "task_enable",
    "task_disable",
    "task_run",
    "task_stop",
    "task_fail",
]


def upgrade() -> None:
    op.execute("ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS check_audit_action")
    action_constraint = " OR ".join([f"action = '{v}'" for v in AUDIT_ACTIONS])
    op.execute(
        f"ALTER TABLE audit_logs ADD CONSTRAINT check_audit_action CHECK ({action_constraint})"
    )


def downgrade() -> None:
    original_actions = [
        "login",
        "logout",
        "refresh",
        "register",
        "verify_email",
        "forgot_password",
        "reset_password",
        "permission_check",
        "role_check",
        "protected_resource_access",
        "create",
        "update",
        "delete",
    ]
    op.execute("ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS check_audit_action")
    action_constraint = " OR ".join([f"action = '{v}'" for v in original_actions])
    op.execute(
        f"ALTER TABLE audit_logs ADD CONSTRAINT check_audit_action CHECK ({action_constraint})"
    )
