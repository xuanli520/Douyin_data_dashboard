"""add_audit_logs_check_constraints

Revision ID: b17da509849c
Revises: be16395279bd
Create Date: 2026-02-09 17:52:05.481619

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b17da509849c"
down_revision: Union[str, Sequence[str], None] = "be16395279bd"
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
]

AUDIT_RESULTS = ["success", "failure", "granted", "denied"]


def upgrade() -> None:
    """Add CHECK constraints for audit_logs action and result fields."""
    conn = op.get_bind()

    result = conn.execute(
        sa.text("""
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'audit_logs'::regclass
        AND conname = 'check_audit_action'
    """)
    )
    if result.scalar() is None:
        op.alter_column("audit_logs", "action", nullable=False)
        action_constraint = " OR ".join([f"action = '{v}'" for v in AUDIT_ACTIONS])
        op.execute(
            f"ALTER TABLE audit_logs ADD CONSTRAINT check_audit_action CHECK ({action_constraint})"
        )

    result = conn.execute(
        sa.text("""
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'audit_logs'::regclass
        AND conname = 'check_audit_result'
    """)
    )
    if result.scalar() is None:
        op.alter_column("audit_logs", "result", nullable=False)
        result_constraint = " OR ".join([f"result = '{v}'" for v in AUDIT_RESULTS])
        op.execute(
            f"ALTER TABLE audit_logs ADD CONSTRAINT check_audit_result CHECK ({result_constraint})"
        )


def downgrade() -> None:
    op.execute("ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS check_audit_action")
    op.execute("ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS check_audit_result")
