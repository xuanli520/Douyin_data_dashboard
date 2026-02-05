from enum import Enum


class ImportStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class FileType(str, Enum):
    EXCEL = "excel"
    CSV = "csv"
