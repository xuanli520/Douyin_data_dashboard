from collections.abc import Sequence

from src.domains.task.enums import TaskDefinitionStatus
from src.shared.errors import ErrorCode


class BusinessException(Exception):
    def __init__(self, code: ErrorCode, msg: str, data: dict | None = None):
        self.code = code
        self.msg = msg
        self.data = data
        super().__init__(msg)

    def __str__(self) -> str:
        return f"[{self.code}] {self.msg}"


class InvalidPasswordException(BusinessException):
    def __init__(self, remaining_attempts: int):
        super().__init__(
            code=ErrorCode.AUTH_INVALID_PASSWORD,
            msg=f"Invalid password, {remaining_attempts} attempts remaining",
            data={"remaining_attempts": remaining_attempts},
        )


class InsufficientPermissionException(BusinessException):
    def __init__(self, required: Sequence[str]):
        super().__init__(
            code=ErrorCode.PERM_INSUFFICIENT,
            msg="Insufficient permissions",
            data={"required": list(required)},
        )


class InsufficientRoleException(BusinessException):
    def __init__(self, required: Sequence[str]):
        super().__init__(
            code=ErrorCode.ROLE_INSUFFICIENT,
            msg="Insufficient roles",
            data={"required": list(required)},
        )


class EndpointInDevelopmentException(BusinessException):
    """端点开发中异常 - 非错误状态"""

    def __init__(
        self,
        data: dict | list | None,
        *,
        is_mock: bool = True,
        expected_release: str | None = None,
    ):
        super().__init__(
            code=ErrorCode.ENDPOINT_IN_DEVELOPMENT,
            msg="该功能正在开发中，当前返回演示数据",
            data={
                "mock": is_mock,
                "expected_release": expected_release,
                "data": data,
            },
        )


class EndpointPlannedException(BusinessException):
    """端点计划中异常"""

    def __init__(self, expected_release: str | None = None):
        data = {"expected_release": expected_release} if expected_release else None
        super().__init__(
            code=ErrorCode.ENDPOINT_PLANNED,
            msg="该功能正在规划中，暂未实现",
            data=data,
        )


class EndpointDeprecatedException(BusinessException):
    """端点已弃用异常（strict mode）"""

    def __init__(self, alternative: str | None = None, removal_date: str | None = None):
        data = {}
        if alternative:
            data["alternative"] = alternative
        if removal_date:
            data["removal_date"] = removal_date
        super().__init__(
            code=ErrorCode.ENDPOINT_DEPRECATED,
            msg="该接口已弃用，请迁移到新接口",
            data=data if data else None,
        )


class AuditInvalidActionException(BusinessException):
    def __init__(self, invalid_value: str):
        super().__init__(
            code=ErrorCode.AUDIT_INVALID_ACTION,
            msg=f"Invalid action: '{invalid_value}'",
            data={"invalid_action": invalid_value},
        )


class AuditInvalidResultException(BusinessException):
    def __init__(self, invalid_value: str):
        super().__init__(
            code=ErrorCode.AUDIT_INVALID_RESULT,
            msg=f"Invalid result: '{invalid_value}'",
            data={"invalid_result": invalid_value},
        )


class AuditInvalidTimeRangeException(BusinessException):
    def __init__(self, occurred_from: str, occurred_to: str):
        super().__init__(
            code=ErrorCode.AUDIT_INVALID_TIME_RANGE,
            msg="occurred_from must be less than or equal to occurred_to",
            data={"occurred_from": occurred_from, "occurred_to": occurred_to},
        )


class AuditConflictActionFiltersException(BusinessException):
    def __init__(self):
        super().__init__(
            code=ErrorCode.AUDIT_CONFLICT_ACTION_FILTERS,
            msg="action and actions cannot be used together",
            data={"action": None, "actions": None},
        )


class TaskNotFoundException(BusinessException):
    def __init__(self, task_id: str):
        super().__init__(
            code=ErrorCode.TASK_NOT_FOUND,
            msg="Task not found",
            data={"task_id": task_id},
        )


class TaskPushFailedException(BusinessException):
    def __init__(self):
        super().__init__(
            code=ErrorCode.TASK_PUSH_FAILED,
            msg="Task push failed: missing task_id",
            data=None,
        )


class TaskTypeUnsupportedException(BusinessException):
    def __init__(self, task_type: str):
        super().__init__(
            code=ErrorCode.TASK_TYPE_UNSUPPORTED,
            msg="Unsupported legacy task_type",
            data={"task_type": task_type},
        )


class TaskStatusBackendUnavailableException(BusinessException):
    def __init__(self):
        super().__init__(
            code=ErrorCode.TASK_STATUS_BACKEND_UNAVAILABLE,
            msg="Task status backend unavailable",
            data=None,
        )


class TaskInvalidStatusException(BusinessException):
    def __init__(self, task_id: str, status: TaskDefinitionStatus):
        super().__init__(
            code=ErrorCode.TASK_INVALID_STATUS,
            msg=f"Task status '{status.value}' cannot be run",
            data={"task_id": task_id, "status": status.value},
        )


class TaskInvalidPayloadException(BusinessException):
    def __init__(self, message: str, field: str):
        super().__init__(
            code=ErrorCode.TASK_INVALID_PAYLOAD,
            msg=message,
            data={"field": field},
        )
