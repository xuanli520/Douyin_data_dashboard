import logging
from sqlalchemy.exc import IntegrityError
from src.exceptions import BusinessException
from src.shared.errors import ErrorCode

logger = logging.getLogger(__name__)

CONSTRAINT_MAPPING = {
    "ix_users_username": ErrorCode.USER_USERNAME_CONFLICT,
    "ix_users_email": ErrorCode.USER_EMAIL_CONFLICT,
    "ix_users_phone": ErrorCode.USER_PHONE_CONFLICT,
}

ERROR_CODE_MESSAGES = {
    ErrorCode.USER_UNIQUE_CONFLICT: "Unique constraint violation",
    ErrorCode.USER_CANNOT_DELETE: "Record is referenced by other data and cannot be deleted",
    ErrorCode.DATABASE_ERROR: "Database constraint error",
}


def _get_sqlstate(e: IntegrityError) -> str:
    orig = getattr(e, "orig", None)
    if not orig:
        return ""
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None) or ""


def _get_constraint_name(e: IntegrityError) -> str:
    orig = getattr(e, "orig", None)
    if not orig:
        return ""
    return getattr(orig, "constraint_name", None) or ""


def _raise_integrity_error(e: IntegrityError):
    sqlstate = _get_sqlstate(e)
    constraint_name = _get_constraint_name(e)

    if sqlstate == "23505":
        error_code = CONSTRAINT_MAPPING.get(
            constraint_name, ErrorCode.USER_UNIQUE_CONFLICT
        )
        field_name_map = {
            ErrorCode.USER_USERNAME_CONFLICT: "username",
            ErrorCode.USER_EMAIL_CONFLICT: "email",
            ErrorCode.USER_PHONE_CONFLICT: "phone",
        }
        field_name = field_name_map.get(error_code, "field")
        msg = f"{field_name} already exists"
        exc = BusinessException(error_code, msg)
        if isinstance(e, BaseException):
            exc.__cause__ = e
        raise exc

    if sqlstate == "23503":
        exc = BusinessException(
            ErrorCode.USER_CANNOT_DELETE,
            ERROR_CODE_MESSAGES[ErrorCode.USER_CANNOT_DELETE],
        )
        if isinstance(e, BaseException):
            exc.__cause__ = e
        raise exc

    logger.warning(
        "Unhandled database constraint error: sqlstate=%s, constraint=%s",
        sqlstate,
        constraint_name,
    )
    exc = BusinessException(
        ErrorCode.DATABASE_ERROR, ERROR_CODE_MESSAGES[ErrorCode.DATABASE_ERROR]
    )
    if isinstance(e, BaseException):
        exc.__cause__ = e
    raise exc
