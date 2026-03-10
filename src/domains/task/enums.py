from enum import StrEnum


class TaskType(StrEnum):
    ETL_ORDERS = "ETL_ORDERS"
    ETL_PRODUCTS = "ETL_PRODUCTS"
    SHOP_DASHBOARD_COLLECTION = "SHOP_DASHBOARD_COLLECTION"


class TaskDefinitionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


class TaskExecutionStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskTriggerMode(StrEnum):
    MANUAL = "MANUAL"
    SCHEDULED = "SCHEDULED"
    SYSTEM = "SYSTEM"
