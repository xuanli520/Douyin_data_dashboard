from typing import Any

from fastapi import Depends, Request
from loguru import logger
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.audit.schemas import AuditAction, AuditLog, AuditResult
from src.audit.filters import AuditLogFilters
from src.session import get_session


class AuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_audit_log(
        self,
        action: AuditAction,
        result: AuditResult,
        actor_id: int | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        user_agent: str | None = None,
        ip: str | None = None,
        extra: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        audit_log = AuditLog(
            request_id=request_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            user_agent=user_agent,
            ip=ip,
            extra=extra,
        )
        self.session.add(audit_log)
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def list_audit_logs(
        self, filters: AuditLogFilters
    ) -> tuple[list[AuditLog], int]:
        stmt = select(AuditLog)
        if filters.action:
            stmt = stmt.where(AuditLog.action == filters.action)
        if filters.actions:
            stmt = stmt.where(AuditLog.action.in_(filters.actions))
        if filters.result:
            stmt = stmt.where(AuditLog.result == filters.result)
        if filters.actor_id is not None:
            stmt = stmt.where(AuditLog.actor_id == filters.actor_id)
        if filters.resource_type:
            stmt = stmt.where(AuditLog.resource_type == filters.resource_type)
        if filters.resource_id:
            stmt = stmt.where(AuditLog.resource_id == filters.resource_id)
        if filters.ip:
            stmt = stmt.where(AuditLog.ip == filters.ip)
        if filters.request_id:
            stmt = stmt.where(AuditLog.request_id == filters.request_id)
        if filters.occurred_from:
            stmt = stmt.where(AuditLog.occurred_at >= filters.occurred_from)
        if filters.occurred_to:
            stmt = stmt.where(AuditLog.occurred_at <= filters.occurred_to)

        total_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(total_stmt)).scalar_one()

        stmt = (
            stmt.order_by(AuditLog.occurred_at.desc())
            .offset((filters.page - 1) * filters.size)
            .limit(filters.size)
        )
        items = (await self.session.execute(stmt)).scalars().all()
        return items, total


class AuditService:
    def __init__(self, repository: AuditRepository):
        self.repository = repository

    async def log(
        self,
        action: AuditAction,
        result: AuditResult,
        actor_id: int | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        user_agent: str | None = None,
        ip: str | None = None,
        extra: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        try:
            await self.repository.create_audit_log(
                action=action,
                result=result,
                actor_id=actor_id,
                resource_type=resource_type,
                resource_id=resource_id,
                user_agent=user_agent,
                ip=ip,
                extra=extra,
                request_id=request_id,
            )
        except Exception:
            logger.exception("Failed to create audit log")

    async def list_logs(self, filters: AuditLogFilters) -> tuple[list[AuditLog], int]:
        return await self.repository.list_audit_logs(filters)


async def get_audit_service(
    session: AsyncSession = Depends(get_session),
) -> AuditService:
    repository = AuditRepository(session=session)
    return AuditService(repository=repository)


def extract_client_info(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ip = forwarded_for.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else None
    return user_agent, ip
