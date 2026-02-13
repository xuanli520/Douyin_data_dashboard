from collections.abc import Sequence

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
        data: dict | None,
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
