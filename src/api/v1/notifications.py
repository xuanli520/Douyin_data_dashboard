from fastapi import APIRouter, Depends

from src.api.v1.mock_data import build_notification_channels, build_notification_test
from src.auth import User, current_user
from src.auth.permissions import NotificationPermission
from src.auth.rbac import require_permissions
from src.core.endpoint_status import in_development
from src.exceptions import EndpointInDevelopmentException

router = APIRouter(prefix="/notifications", tags=["notifications"])
EXPECTED_RELEASE = "2026-04-30"


@router.get("/channels")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def list_notification_channels(
    user: User = Depends(current_user),
    _=Depends(require_permissions(NotificationPermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_notification_channels(),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.post("/channels/{channel_id}/test")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def test_notification_channel(
    channel_id: str,
    user: User = Depends(current_user),
    _=Depends(require_permissions(NotificationPermission.TEST, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_notification_test(channel_id=channel_id),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )
