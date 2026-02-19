from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query

from src.api.v1.mock_data import (
    build_export_create,
    build_export_download,
    build_exports,
)
from src.auth import User, current_user
from src.auth.permissions import ExportPermission
from src.auth.rbac import require_permissions
from src.core.endpoint_status import in_development
from src.exceptions import EndpointInDevelopmentException

router = APIRouter(prefix="/exports", tags=["exports"])
EXPECTED_RELEASE = "2026-04-30"


class ExportCreatePayload(BaseModel):
    name: str
    type: str
    date_range: str | None = None


@router.get("")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def list_exports(
    status: str | None = Query(default=None),
    date_range: str | None = Query(default="30d"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    user: User = Depends(current_user),
    _=Depends(require_permissions(ExportPermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_exports(status=status, date_range=date_range, page=page, size=size),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.post("")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def create_export(
    payload: ExportCreatePayload,
    user: User = Depends(current_user),
    _=Depends(require_permissions(ExportPermission.CREATE, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_export_create(payload.model_dump()),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.get("/{export_id}/download")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def download_export(
    export_id: str,
    user: User = Depends(current_user),
    _=Depends(require_permissions(ExportPermission.DOWNLOAD, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_export_download(export_id=export_id),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )
