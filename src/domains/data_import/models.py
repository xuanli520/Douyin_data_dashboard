from datetime import datetime
from sqlalchemy import DateTime, JSON
from sqlmodel import Field, Relationship, SQLModel

from src.shared.mixins import TimestampMixin
from src.domains.data_import.enums import FileType, ImportStatus


class DataImportRecord(SQLModel, TimestampMixin, table=True):
    __tablename__ = "data_import_records"

    id: int | None = Field(default=None, primary_key=True)
    batch_no: str = Field(max_length=50, unique=True, index=True)

    data_source_id: int | None = Field(
        default=None,
        foreign_key="data_sources.id",
        index=True,
    )

    file_name: str = Field(max_length=255)
    file_type: FileType
    file_size: int
    file_path: str = Field(max_length=500)

    status: ImportStatus = Field(default=ImportStatus.PENDING)

    total_rows: int = Field(default=0)
    success_rows: int = Field(default=0)
    failed_rows: int = Field(default=0)

    field_mapping: dict | None = Field(default=None, sa_type=JSON)

    error_message: str | None = Field(default=None, max_length=1000)

    started_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )

    created_by_id: int | None = Field(default=None, foreign_key="users.id")
    updated_by_id: int | None = Field(default=None, foreign_key="users.id")

    details: list["DataImportDetail"] = Relationship(
        back_populates="import_record",
        cascade_delete=True,
    )


class DataImportDetail(SQLModel, TimestampMixin, table=True):
    __tablename__ = "data_import_details"

    id: int | None = Field(default=None, primary_key=True)

    import_record_id: int = Field(
        foreign_key="data_import_records.id",
        index=True,
        ondelete="CASCADE",
    )

    row_number: int
    row_data: dict | None = Field(default=None, sa_type=JSON)

    status: ImportStatus = Field(default=ImportStatus.PENDING)
    error_message: str | None = Field(default=None, max_length=1000)

    import_record: "DataImportRecord" = Relationship(back_populates="details")
