import pytest
from unittest.mock import AsyncMock, MagicMock
from contextlib import asynccontextmanager

from src.audit.service import AuditRepository, AuditService
from src.audit.schemas import AuditAction, AuditResult


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.in_transaction = MagicMock(return_value=False)

    @asynccontextmanager
    async def _tx_ctx():
        yield session

    session.begin = MagicMock(return_value=_tx_ctx())
    session.begin_nested = MagicMock(return_value=_tx_ctx())
    return session


@pytest.fixture
def audit_repository(mock_session):
    return AuditRepository(mock_session)


@pytest.fixture
def audit_service(audit_repository):
    return AuditService(repository=audit_repository)


@pytest.mark.asyncio
async def test_create_audit_log(audit_repository, mock_session):
    await audit_repository.create_audit_log(
        action=AuditAction.LOGIN,
        result=AuditResult.SUCCESS,
        actor_id=1,
        user_agent="test-agent",
        ip="127.0.0.1",
        extra={"key": "value"},
    )

    mock_session.add.assert_called_once()
    mock_session.begin.assert_called_once()


@pytest.mark.asyncio
async def test_create_audit_log_in_existing_transaction_uses_nested(
    audit_repository, mock_session
):
    mock_session.in_transaction.return_value = True

    await audit_repository.create_audit_log(
        action=AuditAction.LOGIN,
        result=AuditResult.SUCCESS,
        actor_id=1,
    )

    mock_session.begin_nested.assert_called_once()
    mock_session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_log_success(audit_service, mock_session):
    await audit_service.log(
        action=AuditAction.LOGIN,
        result=AuditResult.SUCCESS,
        actor_id=1,
        user_agent="test-agent",
        ip="127.0.0.1",
    )

    mock_session.add.assert_called_once()
    mock_session.begin.assert_called_once()


@pytest.mark.asyncio
async def test_log_handles_exception(audit_service, mock_session):
    mock_session.begin.side_effect = Exception("DB error")

    await audit_service.log(
        action=AuditAction.LOGIN,
        result=AuditResult.FAILURE,
        actor_id=1,
    )


@pytest.mark.asyncio
async def test_list_audit_logs_returns_paginated(mock_session):
    from src.audit.service import AuditService, AuditRepository
    from src.audit.filters import AuditLogFilters
    from unittest.mock import AsyncMock, MagicMock

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar_one.return_value = 0
    mock_session.execute = AsyncMock(return_value=mock_result)

    service = AuditService(AuditRepository(mock_session))
    filters = AuditLogFilters(page=1, size=10)
    items, total = await service.list_logs(filters)
    assert isinstance(items, list)
    assert isinstance(total, int)
