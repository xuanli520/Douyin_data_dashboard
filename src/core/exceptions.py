import logging
from sqlalchemy.exc import IntegrityError
from src.exceptions import BusinessException
from src.shared.errors import ErrorCode

logger = logging.getLogger(__name__)

CONSTRAINT_MAPPING = {
    "ix_users_username": (ErrorCode.USER_USERNAME_CONFLICT, "username"),
    "ix_users_email": (ErrorCode.USER_EMAIL_CONFLICT, "email"),
    "ix_users_phone": (ErrorCode.USER_PHONE_CONFLICT, "phone"),
    "ix_roles_name": (ErrorCode.ROLE_NAME_CONFLICT, "role name"),
    "ix_data_sources_name": (ErrorCode.DATASOURCE_NAME_CONFLICT, "data source name"),
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


def _raise_integrity_error(e: IntegrityError) -> None:
    sqlstate = _get_sqlstate(e)
    constraint_name = _get_constraint_name(e)

    if sqlstate == "23505":
        error_code, field_name = CONSTRAINT_MAPPING.get(
            constraint_name, (ErrorCode.USER_UNIQUE_CONFLICT, "field")
        )
        msg = f"{field_name} already exists"
        raise BusinessException(error_code, msg) from e

    if sqlstate == "23503":
        raise BusinessException(
            ErrorCode.USER_CANNOT_DELETE,
            "Record is referenced by other data and cannot be deleted",
        ) from e

    logger.warning(
        "Unhandled database constraint error: sqlstate=%s, constraint=%s",
        sqlstate,
        constraint_name,
    )
    raise BusinessException(
        ErrorCode.DATABASE_ERROR, "Database constraint error"
    ) from e
