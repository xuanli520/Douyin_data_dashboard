from src.exceptions import BusinessException
from src.shared.errors import ErrorCode


class TaskNotFoundException(BusinessException):
    def __init__(self, task_id: str):
        super().__init__(
            code=ErrorCode.TASK_NOT_FOUND,
            msg=f"Task {task_id} not found",
            data={"task_id": task_id},
        )


class TaskAlreadyRunningException(BusinessException):
    def __init__(self, task_key: str):
        super().__init__(
            code=ErrorCode.TASK_ALREADY_RUNNING,
            msg=f"Task with key {task_key} is already running",
            data={"task_key": task_key},
        )


class ScrapingFailedException(BusinessException):
    def __init__(self, target: str, reason: str):
        super().__init__(
            code=ErrorCode.SCRAPING_FAILED,
            msg=f"Scraping failed for {target}: {reason}",
            data={"target": target, "reason": reason},
        )


class ScrapingRateLimitException(BusinessException):
    def __init__(self, target: str, retry_after: int = 60):
        super().__init__(
            code=ErrorCode.SCRAPING_RATE_LIMIT,
            msg=f"Rate limited for {target}, retry after {retry_after}s",
            data={"target": target, "retry_after": retry_after},
        )


class ETLTransformException(BusinessException):
    def __init__(self, stage: str, details: str):
        super().__init__(
            code=ErrorCode.ETL_TRANSFORM_FAILED,
            msg=f"ETL transform failed at stage: {stage}",
            data={"stage": stage, "details": details},
        )
