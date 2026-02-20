from pydantic import BaseModel
from fastapi import APIRouter, Depends

from src.api.v1.mock_data import (
    build_system_backup,
    build_system_cleanup,
    build_system_config,
    build_system_health,
    build_system_user_settings,
    patch_system_user_settings,
)
from src.auth import User, current_user
from src.auth.permissions import SystemPermission
from src.auth.rbac import require_permissions
from src.core.endpoint_status import in_development
from src.exceptions import EndpointInDevelopmentException

router = APIRouter(prefix="/system", tags=["system"])
EXPECTED_RELEASE = "2026-04-30"


class CleanupPayload(BaseModel):
    retention_days: int = 30
    include_exports: bool = True


class UserSettingsPatchPayload(BaseModel):
    emailNotification: bool | None = None
    pushNotification: bool | None = None
    riskAlert: bool | None = None
    taskReminder: bool | None = None
    twoFactorAuth: bool | None = None
    sessionTimeout: int | None = None
    language: str | None = None
    timezone: str | None = None
    theme: str | None = None


@router.get("/config")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_system_config(
    user: User = Depends(current_user),
    _=Depends(require_permissions(SystemPermission.CONFIG, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_system_config(),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.get("/health")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_system_health(
    user: User = Depends(current_user),
    _=Depends(require_permissions(SystemPermission.HEALTH, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_system_health(),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.post("/backup")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def create_system_backup(
    user: User = Depends(current_user),
    _=Depends(require_permissions(SystemPermission.BACKUP, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_system_backup(),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.post("/cleanup")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def run_system_cleanup(
    payload: CleanupPayload,
    user: User = Depends(current_user),
    _=Depends(require_permissions(SystemPermission.CLEANUP, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_system_cleanup(
            retention_days=payload.retention_days,
            include_exports=payload.include_exports,
        ),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.get("/user-settings")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def get_user_settings(
    user: User = Depends(current_user),
    _=Depends(
        require_permissions(SystemPermission.USER_SETTINGS, bypass_superuser=True)
    ),
):
    raise EndpointInDevelopmentException(
        data=build_system_user_settings(user_id=user.id),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.patch("/user-settings")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def update_user_settings(
    payload: UserSettingsPatchPayload,
    user: User = Depends(current_user),
    _=Depends(
        require_permissions(SystemPermission.USER_SETTINGS, bypass_superuser=True)
    ),
):
    raise EndpointInDevelopmentException(
        data=patch_system_user_settings(
            user_id=user.id,
            payload=payload.model_dump(exclude_none=True),
        ),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )
