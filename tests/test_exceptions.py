import pytest

from src.shared.errors import ErrorCode, NON_ERROR_CODES, error_code_to_http_status
from src.exceptions import (
    BusinessException,
    InsufficientPermissionException,
    InsufficientRoleException,
    InvalidPasswordException,
    EndpointInDevelopmentException,
    EndpointPlannedException,
    EndpointDeprecatedException,
)


@pytest.mark.parametrize(
    "code,msg,data,expected_str",
    [
        (
            ErrorCode.AUTH_INVALID_CREDENTIALS,
            "Invalid credentials",
            None,
            "[10001] Invalid credentials",
        ),
        (
            ErrorCode.BIZ_INSUFFICIENT_BALANCE,
            "Insufficient balance",
            {"balance": 100, "required": 200},
            "[50001] Insufficient balance",
        ),
        (
            ErrorCode.USER_NOT_FOUND,
            "User not found",
            None,
            "[20001] User not found",
        ),
        (
            ErrorCode.PERM_INSUFFICIENT,
            "Permission denied",
            None,
            "[30001] Permission denied",
        ),
        (
            ErrorCode.ROLE_INSUFFICIENT,
            "Role denied",
            None,
            "[30002] Role denied",
        ),
    ],
)
def test_business_exception_exposes_code_message_data_and_string(
    code, msg, data, expected_str
):
    exc = BusinessException(code, msg, data=data)

    assert exc.code == code
    assert exc.msg == msg
    assert exc.data == data
    assert str(exc) == expected_str


def test_domain_exception_includes_remaining_attempts_in_message_and_data():
    exc = InvalidPasswordException(remaining_attempts=3)

    assert exc.code == ErrorCode.AUTH_INVALID_PASSWORD
    assert exc.msg == "Invalid password, 3 attempts remaining"
    assert exc.data == {"remaining_attempts": 3}
    assert str(exc) == "[10002] Invalid password, 3 attempts remaining"


def test_insufficient_permission_exception_includes_required_and_user_perms():
    exc = InsufficientPermissionException(required=["admin:delete", "admin:create"])

    assert exc.code == ErrorCode.PERM_INSUFFICIENT
    assert exc.msg == "Insufficient permissions"
    assert set(exc.data["required"]) == {"admin:delete", "admin:create"}


def test_insufficient_role_exception_includes_required_and_user_roles():
    exc = InsufficientRoleException(required=["admin", "superuser"])

    assert exc.code == ErrorCode.ROLE_INSUFFICIENT
    assert exc.msg == "Insufficient roles"
    assert set(exc.data["required"]) == {"admin", "superuser"}


def test_endpoint_in_development_exception_with_mock_data():
    exc = EndpointInDevelopmentException(
        data={"visitors": 1234},
        is_mock=True,
        expected_release="2026-02-20",
    )

    assert exc.code == ErrorCode.ENDPOINT_IN_DEVELOPMENT
    assert exc.msg == "该功能正在开发中，当前返回演示数据"
    assert exc.data == {
        "mock": True,
        "expected_release": "2026-02-20",
        "data": {"visitors": 1234},
    }


def test_endpoint_in_development_exception_with_real_data():
    exc = EndpointInDevelopmentException(
        data={"real": "value"},
        is_mock=False,
        expected_release=None,
    )

    assert exc.data["mock"] is False
    assert exc.data["expected_release"] is None
    assert exc.data["data"] == {"real": "value"}


def test_endpoint_planned_exception_with_release_date():
    exc = EndpointPlannedException(expected_release="2026-03-01")

    assert exc.code == ErrorCode.ENDPOINT_PLANNED
    assert exc.msg == "该功能正在规划中，暂未实现"
    assert exc.data == {"expected_release": "2026-03-01"}


def test_endpoint_planned_exception_without_release_date():
    exc = EndpointPlannedException()

    assert exc.code == ErrorCode.ENDPOINT_PLANNED
    assert exc.data is None


def test_endpoint_deprecated_exception_with_all_fields():
    exc = EndpointDeprecatedException(
        alternative="/api/v2/legacy",
        removal_date="2026-06-01",
    )

    assert exc.code == ErrorCode.ENDPOINT_DEPRECATED
    assert exc.msg == "该接口已弃用，请迁移到新接口"
    assert exc.data == {
        "alternative": "/api/v2/legacy",
        "removal_date": "2026-06-01",
    }


def test_endpoint_deprecated_exception_with_alternative_only():
    exc = EndpointDeprecatedException(alternative="/api/v2/new")

    assert exc.data == {"alternative": "/api/v2/new"}


def test_endpoint_deprecated_exception_with_removal_date_only():
    exc = EndpointDeprecatedException(removal_date="2026-12-31")

    assert exc.data == {"removal_date": "2026-12-31"}


def test_endpoint_deprecated_exception_without_fields():
    exc = EndpointDeprecatedException()

    assert exc.data is None


def test_endpoint_status_error_codes_http_mapping():
    assert error_code_to_http_status(ErrorCode.ENDPOINT_IN_DEVELOPMENT) == 200
    assert error_code_to_http_status(ErrorCode.ENDPOINT_PLANNED) == 501
    assert error_code_to_http_status(ErrorCode.ENDPOINT_DEPRECATED) == 410


def test_non_error_codes_contains_in_development():
    assert ErrorCode.ENDPOINT_IN_DEVELOPMENT in NON_ERROR_CODES
    assert ErrorCode.ENDPOINT_PLANNED not in NON_ERROR_CODES
    assert ErrorCode.ENDPOINT_DEPRECATED not in NON_ERROR_CODES
