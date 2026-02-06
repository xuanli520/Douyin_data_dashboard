from fastapi import APIRouter, Depends

from src.auth import current_user, User
from src.auth.rbac import PermissionService, get_permission_service
from src.responses.base import Response

router = APIRouter(prefix="/permissions", tags=["permissions"])


@router.get("/me", response_model=Response[dict])
async def get_my_permissions(
    user: User = Depends(current_user),
    permission_service: PermissionService = Depends(get_permission_service),
) -> Response[dict]:
    permissions = await permission_service.repository.get_user_permissions(user.id)
    roles = await permission_service.repository.get_user_roles(user.id)
    return Response.success(
        data={
            "permissions": list(permissions),
            "roles": list(roles),
        }
    )
