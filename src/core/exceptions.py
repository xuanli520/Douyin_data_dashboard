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
    ErrorCode.USER_UNIQUE_CONFLICT: "唯一约束冲突",
    ErrorCode.USER_CANNOT_DELETE: "记录被其他数据引用，无法删除",
    ErrorCode.DATABASE_ERROR: "数据库约束失败",
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
            ErrorCode.USER_USERNAME_CONFLICT: "用户名",
            ErrorCode.USER_EMAIL_CONFLICT: "邮箱",
            ErrorCode.USER_PHONE_CONFLICT: "手机号",
        }
        field_name = field_name_map.get(error_code, "字段")
        msg = f"{field_name}已存在"
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
        "未处理的数据库约束错误: sqlstate=%s, constraint=%s", sqlstate, constraint_name
    )
    exc = BusinessException(
        ErrorCode.DATABASE_ERROR, ERROR_CODE_MESSAGES[ErrorCode.DATABASE_ERROR]
    )
    if isinstance(e, BaseException):
        exc.__cause__ = e
    raise exc
