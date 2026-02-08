from typing import Any

from fastapi import APIRouter, Depends, Query

from src.auth import current_user, User
from src.auth.rbac import require_permissions
from src.auth.permissions import DataSourcePermission
from src.domains.data_source.schemas import (
    DataSourceCreate,
    DataSourceResponse,
    DataSourceStatus,
    DataSourceType,
    DataSourceUpdate,
    ScrapingRuleCreate,
    ScrapingRuleListItem,
    ScrapingRuleResponse,
    ScrapingRuleType,
    ScrapingRuleUpdate,
)
from src.domains.data_source.enums import ScrapingRuleStatus
from src.domains.data_source.services import (
    DataSourceService,
    get_data_source_service,
)
from src.responses.base import Response
from src.shared.schemas import PaginatedData, PaginationParams

router = APIRouter(prefix="/data-sources", tags=["data-source"])
scraping_rule_router = APIRouter(prefix="/scraping-rules", tags=["scraping-rule"])


@router.get("", response_model=PaginatedData[DataSourceResponse])
async def list_data_sources(
    pagination: PaginationParams = Depends(),
    status: DataSourceStatus | None = Query(None),
    source_type: DataSourceType | None = Query(None),
    name: str | None = Query(None, max_length=100),
    service: DataSourceService = Depends(get_data_source_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.VIEW, bypass_superuser=True)),
) -> PaginatedData[DataSourceResponse]:
    ds_list, total = await service.list_paginated(
        page=pagination.page,
        size=pagination.size,
        status=status,
        source_type=source_type,
        name=name,
    )
    return PaginatedData.create(
        items=ds_list, total=total, page=pagination.page, size=pagination.size
    )


@router.post("", response_model=Response[DataSourceResponse])
async def create_data_source(
    data: DataSourceCreate,
    service: DataSourceService = Depends(get_data_source_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.CREATE, bypass_superuser=True)),
) -> Response[DataSourceResponse]:
    ds = await service.create(data, user_id=user.id)
    return Response.success(data=ds)


@router.get("/{ds_id}", response_model=Response[DataSourceResponse])
async def get_data_source(
    ds_id: int,
    service: DataSourceService = Depends(get_data_source_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.VIEW, bypass_superuser=True)),
) -> Response[DataSourceResponse]:
    ds = await service.get_by_id(ds_id)
    return Response.success(data=ds)


@router.put("/{ds_id}", response_model=Response[DataSourceResponse])
async def update_data_source(
    ds_id: int,
    data: DataSourceUpdate,
    service: DataSourceService = Depends(get_data_source_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.UPDATE, bypass_superuser=True)),
) -> Response[DataSourceResponse]:
    ds = await service.update(ds_id, data, user_id=user.id)
    return Response.success(data=ds)


@router.delete("/{ds_id}", response_model=Response[None])
async def delete_data_source(
    ds_id: int,
    service: DataSourceService = Depends(get_data_source_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.DELETE, bypass_superuser=True)),
) -> Response[None]:
    await service.delete(ds_id)
    return Response.success()


@router.post("/{ds_id}/activate", response_model=Response[DataSourceResponse])
async def activate_data_source(
    ds_id: int,
    service: DataSourceService = Depends(get_data_source_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.UPDATE, bypass_superuser=True)),
) -> Response[DataSourceResponse]:
    ds = await service.activate(ds_id, user_id=user.id)
    return Response.success(data=ds)


@router.post("/{ds_id}/deactivate", response_model=Response[DataSourceResponse])
async def deactivate_data_source(
    ds_id: int,
    service: DataSourceService = Depends(get_data_source_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.UPDATE, bypass_superuser=True)),
) -> Response[DataSourceResponse]:
    ds = await service.deactivate(ds_id, user_id=user.id)
    return Response.success(data=ds)


@router.post("/{ds_id}/validate", response_model=Response[dict[str, Any]])
async def validate_connection(
    ds_id: int,
    service: DataSourceService = Depends(get_data_source_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.VIEW, bypass_superuser=True)),
) -> Response[dict[str, Any]]:
    result = await service.validate_connection(ds_id)
    return Response.success(data=result)


@router.get("/{ds_id}/scraping-rules", response_model=Response[list[Any]])
async def list_scraping_rules_by_datasource(
    ds_id: int,
    service: DataSourceService = Depends(get_data_source_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.VIEW, bypass_superuser=True)),
) -> Response[list[Any]]:
    rules = await service.list_scraping_rules(ds_id)
    return Response.success(data=rules)


@scraping_rule_router.post("", response_model=Response[ScrapingRuleResponse])
async def create_scraping_rule(
    data: ScrapingRuleCreate,
    service: DataSourceService = Depends(get_data_source_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.CREATE, bypass_superuser=True)),
) -> Response[ScrapingRuleResponse]:
    rule = await service.create_scraping_rule(data.data_source_id, data)
    return Response.success(data=rule)


@scraping_rule_router.get("", response_model=PaginatedData[ScrapingRuleListItem])
async def list_scraping_rules(
    pagination: PaginationParams = Depends(),
    name: str | None = Query(None, max_length=100),
    rule_type: ScrapingRuleType | None = Query(None),
    status: ScrapingRuleStatus | None = Query(None),
    data_source_id: int | None = Query(None, ge=1),
    service: DataSourceService = Depends(get_data_source_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.VIEW, bypass_superuser=True)),
) -> PaginatedData[ScrapingRuleListItem]:
    rules, total = await service.list_scraping_rules_paginated(
        page=pagination.page,
        size=pagination.size,
        name=name,
        rule_type=rule_type,
        status=status,
        data_source_id=data_source_id,
    )
    return PaginatedData.create(
        items=rules, total=total, page=pagination.page, size=pagination.size
    )


@scraping_rule_router.put("/{rule_id}", response_model=Response[ScrapingRuleResponse])
async def update_scraping_rule(
    rule_id: int,
    data: ScrapingRuleUpdate,
    service: DataSourceService = Depends(get_data_source_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.UPDATE, bypass_superuser=True)),
) -> Response[ScrapingRuleResponse]:
    rule = await service.update_scraping_rule(rule_id, data)
    return Response.success(data=rule)


@scraping_rule_router.get("/{rule_id}", response_model=Response[ScrapingRuleResponse])
async def get_scraping_rule(
    rule_id: int,
    service: DataSourceService = Depends(get_data_source_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.VIEW, bypass_superuser=True)),
) -> Response[ScrapingRuleResponse]:
    rule = await service.get_scraping_rule(rule_id)
    return Response.success(data=rule)


@scraping_rule_router.delete("/{rule_id}", response_model=Response[None])
async def delete_scraping_rule(
    rule_id: int,
    service: DataSourceService = Depends(get_data_source_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.DELETE, bypass_superuser=True)),
) -> Response[None]:
    await service.delete_scraping_rule(rule_id)
    return Response.success()
