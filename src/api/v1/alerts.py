from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query

from src.api.v1.mock_data import (
    build_alert_action,
    build_alert_rules,
    build_alerts,
    build_created_alert_rule,
)
from src.auth import User, current_user
from src.auth.permissions import AlertPermission
from src.auth.rbac import require_permissions
from src.core.endpoint_status import in_development
from src.exceptions import EndpointInDevelopmentException

router = APIRouter(prefix="/alerts", tags=["alerts"])
EXPECTED_RELEASE = "2026-04-30"


class AlertAssignPayload(BaseModel):
    assignee: str


class AlertRulePayload(BaseModel):
    name: str
    metric: str
    threshold: str
    level: str = "warning"


@router.get("")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def list_alerts(
    level: str | None = Query(default=None),
    status: str | None = Query(default=None),
    assignee: str | None = Query(default=None),
    shop_id: int | None = Query(default=None),
    date_range: str | None = Query(default="30d"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    user: User = Depends(current_user),
    _=Depends(require_permissions(AlertPermission.VIEW, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_alerts(
            level=level,
            status=status,
            assignee=assignee,
            shop_id=shop_id,
            date_range=date_range,
            page=page,
            size=size,
        ),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.get("/rules")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def list_alert_rules(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    user: User = Depends(current_user),
    _=Depends(require_permissions(AlertPermission.RULE, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_alert_rules(page=page, size=size),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.post("/rules")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def create_alert_rule(
    payload: AlertRulePayload,
    user: User = Depends(current_user),
    _=Depends(require_permissions(AlertPermission.RULE, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_created_alert_rule(payload.model_dump()),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.post("/{alert_id}/assign")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def assign_alert(
    alert_id: str,
    payload: AlertAssignPayload,
    user: User = Depends(current_user),
    _=Depends(require_permissions(AlertPermission.ASSIGN, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_alert_action(
            alert_id=alert_id, action="assign", assignee=payload.assignee
        ),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.post("/{alert_id}/resolve")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def resolve_alert(
    alert_id: str,
    user: User = Depends(current_user),
    _=Depends(require_permissions(AlertPermission.RESOLVE, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_alert_action(alert_id=alert_id, action="resolve"),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.post("/{alert_id}/ignore")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def ignore_alert(
    alert_id: str,
    user: User = Depends(current_user),
    _=Depends(require_permissions(AlertPermission.IGNORE, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_alert_action(alert_id=alert_id, action="ignore"),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )


@router.post("/{alert_id}/acknowledge")
@in_development(mock_data={}, expected_release=EXPECTED_RELEASE, prefer_real=True)
async def acknowledge_alert(
    alert_id: str,
    user: User = Depends(current_user),
    _=Depends(require_permissions(AlertPermission.ACKNOWLEDGE, bypass_superuser=True)),
):
    raise EndpointInDevelopmentException(
        data=build_alert_action(alert_id=alert_id, action="acknowledge"),
        is_mock=True,
        expected_release=EXPECTED_RELEASE,
    )
