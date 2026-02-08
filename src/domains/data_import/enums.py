from enum import StrEnum


class ImportStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    VALIDATION_FAILED = "VALIDATION_FAILED"


class FileType(StrEnum):
    EXCEL = "EXCEL"
    CSV = "CSV"
