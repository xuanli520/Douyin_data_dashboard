from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.data_source.config_mapper import ScrapingRuleConfigMapper
from src.domains.data_source.enums import (
    DataSourceStatus,
    ScrapingRuleStatus,
    TargetType,
)
from src.domains.data_source.repository import DataSourceRepository
from src.domains.scraping_rule.models import ScrapingRule
from src.domains.scraping_rule.repository import ScrapingRuleRepository
from src.domains.scraping_rule.schemas import (
    ScrapingRuleCreate,
    ScrapingRuleListItem,
    ScrapingRuleResponse,
    ScrapingRuleUpdate,
)
from src.exceptions import BusinessException
from src.scrapers.shop_dashboard.shop_selection_validator import (
    ensure_explicit_shop_selection_valid,
    has_explicit_shop_selection,
    normalize_shop_selection_payload,
)
from src.session import get_session
from src.shared.errors import ErrorCode


class ScrapingRuleService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.ds_repo = DataSourceRepository(session=session)
        self.rule_repo = ScrapingRuleRepository(session=session)

    async def create_rule(
        self,
        *,
        data_source_id: int,
        name: str,
        target_type: TargetType,
        config: dict[str, Any],
        description: str | None = None,
        is_active: bool = True,
    ) -> ScrapingRuleResponse:
        ds = await self.ds_repo.get_by_id(data_source_id)
        if not ds:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND, "DataSource not found"
            )
        if ds.status != DataSourceStatus.ACTIVE:
            raise BusinessException(
                ErrorCode.DATA_VALIDATION_FAILED,
                "Cannot create rule for inactive data source",
            )

        rule_data = {
            "data_source_id": data_source_id,
            "name": name,
            "target_type": target_type,
            "description": description,
            "status": (
                ScrapingRuleStatus.ACTIVE if is_active else ScrapingRuleStatus.INACTIVE
            ),
            "version": 1,
        }
        normalized_config = normalize_shop_selection_payload(config)
        if has_explicit_shop_selection(config):
            try:
                ensure_explicit_shop_selection_valid(normalized_config)
            except ValueError as exc:
                raise BusinessException(
                    ErrorCode.DATA_VALIDATION_FAILED,
                    str(exc),
                ) from exc
        rule_data.update(
            ScrapingRuleConfigMapper.map_to_model_fields(normalized_config)
        )
        rule = await self.rule_repo.create(rule_data)
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return self._build_scraping_rule_response(rule)

    async def create(self, data: ScrapingRuleCreate) -> ScrapingRuleResponse:
        return await self.create_rule(
            data_source_id=data.data_source_id,
            name=data.name,
            target_type=data.target_type,
            config=data.config,
            description=data.description,
            is_active=data.is_active,
        )

    async def list_rules_by_data_source(
        self, data_source_id: int
    ) -> list[ScrapingRuleResponse]:
        ds = await self.ds_repo.get_by_id(data_source_id)
        if not ds:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND, "DataSource not found"
            )

        rules = await self.rule_repo.get_by_data_source(data_source_id)
        return [self._build_scraping_rule_response(rule) for rule in rules]

    async def list_rules_paginated(
        self,
        *,
        page: int,
        size: int,
        name: str | None = None,
        target_type: TargetType | None = None,
        status: ScrapingRuleStatus | None = None,
        data_source_id: int | None = None,
    ) -> tuple[list[ScrapingRuleListItem], int]:
        rules, total = await self.rule_repo.get_paginated(
            page=page,
            size=size,
            name=name,
            rule_type=target_type,
            status=ScrapingRuleStatus(status.value.upper()) if status else None,
            data_source_id=data_source_id,
        )
        return [self._build_scraping_rule_list_item(rule) for rule in rules], total

    async def get_rule(self, rule_id: int) -> ScrapingRuleResponse:
        rule = await self.rule_repo.get_by_id(rule_id)
        if not rule:
            raise BusinessException(
                ErrorCode.SCRAPING_RULE_NOT_FOUND, "ScrapingRule not found"
            )
        return self._build_scraping_rule_response(rule)

    async def update_rule(
        self,
        rule_id: int,
        data: ScrapingRuleUpdate,
    ) -> ScrapingRuleResponse:
        rule = await self.rule_repo.get_by_id(rule_id)
        if not rule:
            raise BusinessException(
                ErrorCode.SCRAPING_RULE_NOT_FOUND, "ScrapingRule not found"
            )

        update_data: dict[str, Any] = {}
        if data.name is not None:
            update_data["name"] = data.name
        if data.description is not None:
            update_data["description"] = data.description
        if data.is_active is not None:
            update_data["status"] = (
                ScrapingRuleStatus.ACTIVE
                if data.is_active
                else ScrapingRuleStatus.INACTIVE
            )
        if data.config is not None:
            normalized_config = normalize_shop_selection_payload(data.config)
            if has_explicit_shop_selection(data.config):
                try:
                    ensure_explicit_shop_selection_valid(normalized_config)
                except ValueError as exc:
                    raise BusinessException(
                        ErrorCode.DATA_VALIDATION_FAILED,
                        str(exc),
                    ) from exc
            update_data.update(
                ScrapingRuleConfigMapper.map_to_model_fields(normalized_config)
            )
        if update_data:
            update_data["version"] = (rule.version or 1) + 1

        rule = await self.rule_repo.update(rule_id, update_data)
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return self._build_scraping_rule_response(rule)

    async def delete_rule(self, rule_id: int) -> None:
        await self.rule_repo.delete(rule_id)
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    def _build_scraping_rule_response(self, rule: ScrapingRule) -> ScrapingRuleResponse:
        return ScrapingRuleResponse(
            id=rule.id if rule.id is not None else 0,
            data_source_id=rule.data_source_id
            if rule.data_source_id is not None
            else 0,
            name=rule.name,
            target_type=rule.target_type,
            config=ScrapingRuleConfigMapper.build_config_from_model(rule),
            is_active=rule.status == ScrapingRuleStatus.ACTIVE,
            status=rule.status,
            version=rule.version,
            description=rule.description,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )

    def _build_scraping_rule_list_item(
        self, rule: ScrapingRule
    ) -> ScrapingRuleListItem:
        return ScrapingRuleListItem(
            id=rule.id if rule.id is not None else 0,
            data_source_id=rule.data_source_id
            if rule.data_source_id is not None
            else 0,
            name=rule.name,
            target_type=rule.target_type,
            config=ScrapingRuleConfigMapper.build_config_from_model(rule),
            is_active=rule.status == ScrapingRuleStatus.ACTIVE,
            status=rule.status,
            version=rule.version,
            description=rule.description,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
            data_source_name=rule.data_source.name if rule.data_source else None,
        )


async def get_scraping_rule_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[ScrapingRuleService, None]:
    yield ScrapingRuleService(session=session)
