from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from src.auth import User, current_user
from src.auth.permissions import ShopDashboardPermission
from src.auth.rbac import require_permissions
from src.domains.agent_result.schemas import (
    AgentResultListResponse,
    AgentResultResponse,
)
from src.domains.agent_result.services import (
    AgentResultService,
    get_agent_result_service,
)
from src.responses.base import Response

router = APIRouter(prefix="/agent-results", tags=["agent-results"])


@router.get("/download", response_class=StreamingResponse)
async def download_agent_results_csv(
    namespace: str = Query(..., min_length=1),
    resource_key: str = Query(..., min_length=1),
    date_from: date = Query(...),
    date_to: date = Query(...),
    _user: User = Depends(current_user),
    _=Depends(
        require_permissions(ShopDashboardPermission.QUERY, bypass_superuser=True)
    ),
    service: AgentResultService = Depends(get_agent_result_service),
) -> StreamingResponse:
    csv_content, filename = await service.build_csv(
        namespace=namespace,
        resource_key=resource_key,
        date_from=date_from,
        date_to=date_to,
    )
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("", response_model=Response[AgentResultListResponse])
async def list_agent_results(
    namespace: str | None = Query(default=None),
    resource_key: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    _user: User = Depends(current_user),
    _=Depends(
        require_permissions(ShopDashboardPermission.QUERY, bypass_superuser=True)
    ),
    service: AgentResultService = Depends(get_agent_result_service),
) -> Response[AgentResultListResponse]:
    data = await service.list_results(
        namespace=namespace,
        resource_key=resource_key,
        date_from=date_from,
        date_to=date_to,
        page=page,
        size=size,
    )
    return Response.success(data=data)


@router.get("/{result_id}", response_model=Response[AgentResultResponse])
async def get_agent_result(
    result_id: int,
    _user: User = Depends(current_user),
    _=Depends(
        require_permissions(ShopDashboardPermission.QUERY, bypass_superuser=True)
    ),
    service: AgentResultService = Depends(get_agent_result_service),
) -> Response[AgentResultResponse]:
    data = await service.get_result(result_id)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="agent result not found",
        )
    return Response.success(data=data)
