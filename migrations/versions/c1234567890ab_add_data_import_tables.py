"""add data_import_records and data_import_details tables

Revision ID: c1234567890ab
Revises: b25a49dc83a2
Create Date: 2026-02-05 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "c1234567890ab"
down_revision: Union[str, Sequence[str], None] = "b25a49dc83a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_import_records",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "batch_no", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False
        ),
        sa.Column("data_source_id", sa.Integer(), nullable=True),
        sa.Column(
            "file_name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False
        ),
        sa.Column(
            "file_type",
            sa.Enum("EXCEL", "CSV", name="filetype"),
            nullable=False,
        ),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column(
            "file_path", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "PROCESSING",
                "SUCCESS",
                "FAILED",
                "PARTIAL",
                name="importstatus",
            ),
            nullable=False,
        ),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("success_rows", sa.Integer(), nullable=False),
        sa.Column("failed_rows", sa.Integer(), nullable=False),
        sa.Column("field_mapping", sa.JSON(), nullable=True),
        sa.Column(
            "error_message",
            sqlmodel.sql.sqltypes.AutoString(length=1000),
            nullable=True,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["data_sources.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_data_import_records_batch_no"),
        "data_import_records",
        ["batch_no"],
        unique=True,
    )
    op.create_index(
        op.f("ix_data_import_records_data_source_id"),
        "data_import_records",
        ["data_source_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_data_import_records_status"),
        "data_import_records",
        ["status"],
        unique=False,
    )
    op.create_table(
        "data_import_details",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("import_record_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("row_data", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "PROCESSING",
                "SUCCESS",
                "FAILED",
                "PARTIAL",
                name="importstatus",
            ),
            nullable=False,
        ),
        sa.Column(
            "error_message",
            sqlmodel.sql.sqltypes.AutoString(length=1000),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["import_record_id"],
            ["data_import_records.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_data_import_details_import_record_id"),
        "data_import_details",
        ["import_record_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_data_import_details_import_record_id"),
        table_name="data_import_details",
    )
    op.drop_table("data_import_details")
    op.drop_index(
        op.f("ix_data_import_records_status"), table_name="data_import_records"
    )
    op.drop_index(
        op.f("ix_data_import_records_data_source_id"), table_name="data_import_records"
    )
    op.drop_index(
        op.f("ix_data_import_records_batch_no"), table_name="data_import_records"
    )
    op.drop_table("data_import_records")
