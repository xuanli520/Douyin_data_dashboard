from sqlalchemy import JSON, Index
from sqlmodel import Field, SQLModel

from src.domains.collection_job.enums import CollectionJobStatus
from src.domains.task.enums import TaskType
from src.shared.mixins import TimestampMixin


class CollectionJob(SQLModel, TimestampMixin, table=True):
    __tablename__ = "collection_jobs"
    __table_args__ = (
        Index("idx_collection_jobs_task_type_status", "task_type", "status"),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100, index=True)
    task_type: TaskType = Field(index=True)
    data_source_id: int = Field(
        foreign_key="data_sources.id",
        index=True,
        ondelete="CASCADE",
    )
    rule_id: int = Field(
        foreign_key="scraping_rules.id",
        index=True,
        ondelete="CASCADE",
    )
    schedule: dict = Field(default_factory=dict, sa_type=JSON)
    status: CollectionJobStatus = Field(
        default=CollectionJobStatus.ACTIVE,
        index=True,
    )
