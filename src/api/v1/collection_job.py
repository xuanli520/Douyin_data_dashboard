from fastapi import APIRouter, Depends, Query

from src.auth import User, current_user
from src.auth.permissions import DataSourcePermission
from src.auth.rbac import require_permissions
from src.domains.collection_job.schemas import (
    CollectionJobCreate,
    CollectionJobResponse,
)
from src.domains.collection_job.services import (
    CollectionJobService,
    get_collection_job_service,
)
from src.domains.task.enums import TaskType
from src.responses.base import Response

router = APIRouter(prefix="/collection-jobs", tags=["collection-job"])


@router.post("", response_model=Response[CollectionJobResponse])
async def create_collection_job(
    data: CollectionJobCreate,
    service: CollectionJobService = Depends(get_collection_job_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.CREATE, bypass_superuser=True)),
) -> Response[CollectionJobResponse]:
    job = await service.create(data)
    return Response.success(data=job)


@router.get("", response_model=Response[list[CollectionJobResponse]])
async def list_collection_jobs(
    task_type: TaskType | None = Query(None),
    service: CollectionJobService = Depends(get_collection_job_service),
    user: User = Depends(current_user),
    _=Depends(require_permissions(DataSourcePermission.VIEW, bypass_superuser=True)),
) -> Response[list[CollectionJobResponse]]:
    jobs = await service.list_enabled_jobs(task_type=task_type)
    return Response.success(data=jobs)
