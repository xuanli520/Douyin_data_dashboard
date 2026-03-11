from typing import Any

from fastapi import APIRouter, Depends, Query

from src.auth import User, current_user
from src.auth.permissions import DataSourcePermission
from src.auth.rbac import require_permissions
from src.domains.data_source.enums import ScrapingRuleStatus, TargetType
from src.domains.scraping_rule.schemas import (
    ScrapingRuleCreate,
    ScrapingRuleListItem,
    ScrapingRuleResponse,
    ScrapingRuleUpdate,
)
from src.domains.scraping_rule.services import (
    ScrapingRuleService,
    get_scraping_rule_service,
)
from src.responses.base import Response
from src.shared.schemas import PaginatedData, PaginationParams

router = APIRouter(tags=["scraping-rule"])


@router.get("/data-sources/{ds_id}/scraping-rules", response_model=Response[list[Any]])
async def list_scraping_rules_by_datasource(
    ds_id: int,
    service: ScrapingRuleService = Depends(get_scraping_rule_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.VIEW, bypass_superuser=True)),
) -> Response[list[Any]]:
    rules = await service.list_rules_by_data_source(ds_id)
    return Response.success(data=rules)


@router.post("/scraping-rules", response_model=Response[ScrapingRuleResponse])
async def create_scraping_rule(
    data: ScrapingRuleCreate,
    service: ScrapingRuleService = Depends(get_scraping_rule_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.CREATE, bypass_superuser=True)),
) -> Response[ScrapingRuleResponse]:
    rule = await service.create(data)
    return Response.success(data=rule)


@router.get("/scraping-rules", response_model=PaginatedData[ScrapingRuleListItem])
async def list_scraping_rules(
    pagination: PaginationParams = Depends(),
    name: str | None = Query(None, max_length=100),
    target_type: TargetType | None = Query(None),
    status: ScrapingRuleStatus | None = Query(None),
    data_source_id: int | None = Query(None, ge=1),
    service: ScrapingRuleService = Depends(get_scraping_rule_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.VIEW, bypass_superuser=True)),
) -> PaginatedData[ScrapingRuleListItem]:
    rules, total = await service.list_rules_paginated(
        page=pagination.page,
        size=pagination.size,
        name=name,
        target_type=target_type,
        status=status,
        data_source_id=data_source_id,
    )
    return PaginatedData.create(
        items=rules, total=total, page=pagination.page, size=pagination.size
    )


@router.put("/scraping-rules/{rule_id}", response_model=Response[ScrapingRuleResponse])
async def update_scraping_rule(
    rule_id: int,
    data: ScrapingRuleUpdate,
    service: ScrapingRuleService = Depends(get_scraping_rule_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.UPDATE, bypass_superuser=True)),
) -> Response[ScrapingRuleResponse]:
    rule = await service.update_rule(rule_id, data)
    return Response.success(data=rule)


@router.get("/scraping-rules/{rule_id}", response_model=Response[ScrapingRuleResponse])
async def get_scraping_rule(
    rule_id: int,
    service: ScrapingRuleService = Depends(get_scraping_rule_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.VIEW, bypass_superuser=True)),
) -> Response[ScrapingRuleResponse]:
    rule = await service.get_rule(rule_id)
    return Response.success(data=rule)


@router.delete("/scraping-rules/{rule_id}", response_model=Response[None])
async def delete_scraping_rule(
    rule_id: int,
    service: ScrapingRuleService = Depends(get_scraping_rule_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.DELETE, bypass_superuser=True)),
) -> Response[None]:
    await service.delete_rule(rule_id)
    return Response.success()
