import pytest
from src.core.exceptions import (
    _get_sqlstate,
    _get_constraint_name,
    _raise_integrity_error,
)
from src.exceptions import BusinessException
from src.shared.errors import ErrorCode as SrcErrorCode


def test_get_sqlstate_asyncpg():
    class MockOrig:
        sqlstate = "23505"

    class MockExc:
        orig = MockOrig()

    assert _get_sqlstate(MockExc()) == "23505"


def test_get_sqlstate_psycopg2():
    class MockOrig:
        pgcode = "23503"

    class MockExc:
        orig = MockOrig()

    assert _get_sqlstate(MockExc()) == "23503"


def test_get_sqlstate_no_orig():
    class MockExc:
        orig = None

    assert _get_sqlstate(MockExc()) == ""


def test_get_constraint_name_direct():
    class MockOrig:
        constraint_name = "ix_users_username"

    class MockExc:
        orig = MockOrig()

    assert _get_constraint_name(MockExc()) == "ix_users_username"


def test_get_constraint_name_no_orig():
    class MockExc:
        orig = None

    assert _get_constraint_name(MockExc()) == ""


def test_raise_integrity_error_username_conflict():
    class MockOrig:
        sqlstate = "23505"
        constraint_name = "ix_users_username"

    class MockExc:
        orig = MockOrig()

    with pytest.raises(BusinessException) as exc_info:
        _raise_integrity_error(MockExc())
    assert exc_info.value.code == SrcErrorCode.USER_USERNAME_CONFLICT


def test_raise_integrity_error_email_conflict():
    class MockOrig:
        sqlstate = "23505"
        constraint_name = "ix_users_email"

    class MockExc:
        orig = MockOrig()

    with pytest.raises(BusinessException) as exc_info:
        _raise_integrity_error(MockExc())
    assert exc_info.value.code == SrcErrorCode.USER_EMAIL_CONFLICT


def test_raise_integrity_error_unknown_unique():
    class MockOrig:
        sqlstate = "23505"
        constraint_name = "ix_other_table_column"

    class MockExc:
        orig = MockOrig()

    with pytest.raises(BusinessException) as exc_info:
        _raise_integrity_error(MockExc())
    assert exc_info.value.code == SrcErrorCode.USER_UNIQUE_CONFLICT


def test_raise_integrity_error_foreign_key_violation():
    class MockOrig:
        sqlstate = "23503"
        constraint_name = "data_sources_created_by_id_fkey"

    class MockExc:
        orig = MockOrig()

    with pytest.raises(BusinessException) as exc_info:
        _raise_integrity_error(MockExc())
    assert exc_info.value.code == SrcErrorCode.USER_CANNOT_DELETE


def test_raise_integrity_error_unknown_sqlstate():
    class MockOrig:
        sqlstate = "99999"
        constraint_name = "some_constraint"

    class MockExc:
        orig = MockOrig()

    with pytest.raises(BusinessException) as exc_info:
        _raise_integrity_error(MockExc())
    assert exc_info.value.code == SrcErrorCode.DATABASE_ERROR
