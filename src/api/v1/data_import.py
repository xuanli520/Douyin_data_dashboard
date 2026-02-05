import os
import shutil
import uuid
from typing import Any

from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import current_user, User
from src.cache import get_cache, CacheProtocol
from src.domains.data_import.enums import ImportStatus
from src.domains.data_import.schemas import (
    ImportUploadResponse,
    FieldMappingRequest,
    ImportValidateResponse,
    ImportConfirmResponse,
    ImportHistoryResponse,
    ImportDetailResponse,
    ImportCancelResponse,
)
from src.domains.data_import.service import ImportService
from src.responses.base import Response
from src.session import get_session


router = APIRouter()


def get_import_service(
    session: AsyncSession = Depends(get_session),
    cache: CacheProtocol = Depends(get_cache),
) -> ImportService:
    redis = cache if hasattr(cache, "set") else None
    return ImportService(session=session, redis=redis)


@router.post("/upload", response_model=Response[ImportUploadResponse])
async def upload_file(
    file: UploadFile = File(...),
    data_source_id: int = Form(...),
    current_user: User = Depends(current_user),
    service: ImportService = Depends(get_import_service),
):
    upload_dir = "uploads/imports"
    os.makedirs(upload_dir, exist_ok=True)

    filename = file.filename or "unknown"
    file_ext = os.path.splitext(filename)[1]
    unique_filename = f"{uuid.uuid4().hex}{file_ext}"
    file_path = os.path.join(upload_dir, unique_filename)

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    content = await file.read()
    file_size = len(content)

    batch_no = f"IMP-{uuid.uuid4().hex[:8].upper()}"

    record = await service.upload_file(
        file_path=file_path,
        file_name=filename,
        file_size=file_size,
        data_source_id=data_source_id,
        user_id=current_user.id,
        batch_no=batch_no,
    )

    return Response.success(
        data=ImportUploadResponse(
            id=record.id,
            file_name=record.file_name,
            file_size=record.file_size,
            status=record.status.value,
            created_at=record.created_at,
        )
    )


@router.post("/parse", response_model=Response[dict[str, Any]])
async def parse_file(
    import_id: int,
    current_user: User = Depends(current_user),
    service: ImportService = Depends(get_import_service),
):
    record = await service.repo.get_by_id(import_id)
    if not record:
        return Response.error(code=404, msg="Import record not found")

    if record.created_by_id != current_user.id:
        return Response.error(code=403, msg="Access denied")

    rows = await service.parse_file(import_id)

    preview = rows[:5]

    return Response.success(
        data={
            "id": import_id,
            "total_rows": len(rows),
            "preview": preview,
        }
    )


@router.post("/mapping", response_model=Response[dict[str, Any]])
async def apply_mapping(
    import_id: int,
    request: FieldMappingRequest,
    current_user: User = Depends(current_user),
    service: ImportService = Depends(get_import_service),
):
    record = await service.repo.get_by_id(import_id)
    if not record:
        return Response.error(code=404, msg="Import record not found")

    if record.created_by_id != current_user.id:
        return Response.error(code=403, msg="Access denied")

    await service.apply_mapping(
        import_id=import_id,
        mappings=request.mappings,
        target_fields=request.target_fields,
    )

    return Response.success(data={"id": import_id, "status": "mapped"})


@router.post("/validate", response_model=Response[ImportValidateResponse])
async def validate_data(
    import_id: int,
    current_user: User = Depends(current_user),
    service: ImportService = Depends(get_import_service),
):
    record = await service.repo.get_by_id(import_id)
    if not record:
        return Response.error(code=404, msg="Import record not found")

    if record.created_by_id != current_user.id:
        return Response.error(code=403, msg="Access denied")

    rows = await service.parse_file(import_id)
    results = await service.validate_data(import_id, rows)

    return Response.success(
        data=ImportValidateResponse(
            id=import_id,
            total_rows=results["total_rows"],
            passed=results["passed"],
            failed=results["failed"],
            errors_by_field=results["errors_by_field"],
            warnings_by_field=results["warnings_by_field"],
        )
    )


@router.post("/confirm", response_model=Response[ImportConfirmResponse])
async def confirm_import(
    import_id: int,
    current_user: User = Depends(current_user),
    service: ImportService = Depends(get_import_service),
):
    record = await service.repo.get_by_id(import_id)
    if not record:
        return Response.error(code=404, msg="Import record not found")

    if record.created_by_id != current_user.id:
        return Response.error(code=403, msg="Access denied")

    rows = await service.parse_file(import_id)
    result = await service.confirm_import(import_id, rows)

    return Response.success(
        data=ImportConfirmResponse(
            id=import_id,
            total=result["total"],
            success=result["success"],
            failed=result["failed"],
            errors=result["errors"],
        )
    )


@router.get("/history", response_model=Response[ImportHistoryResponse])
async def list_import_history(
    page: int = 1,
    size: int = 20,
    current_user: User = Depends(current_user),
    service: ImportService = Depends(get_import_service),
):
    items, total = await service.list_import_history(
        user_id=current_user.id,
        page=page,
        size=size,
    )

    return Response.success(
        data=ImportHistoryResponse(
            items=items,
            total=total,
            page=page,
            size=size,
        )
    )


@router.get("/{import_id}", response_model=Response[ImportDetailResponse])
async def get_import_detail(
    import_id: int,
    current_user: User = Depends(current_user),
    service: ImportService = Depends(get_import_service),
):
    record = await service.get_import_detail(import_id)
    if not record:
        return Response.error(code=404, msg="Import record not found")

    if record.created_by_id != current_user.id:
        return Response.error(code=403, msg="Access denied")

    return Response.success(
        data=ImportDetailResponse(
            id=record.id,
            file_name=record.file_name,
            file_path=record.file_path,
            file_size=record.file_size,
            status=record.status.value,
            field_mapping=record.field_mapping,
            total_rows=record.total_rows,
            success_rows=record.success_rows,
            failed_rows=record.failed_rows,
            error_message=record.error_message,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
    )


@router.post("/{import_id}/cancel", response_model=Response[ImportCancelResponse])
async def cancel_import(
    import_id: int,
    current_user: User = Depends(current_user),
    service: ImportService = Depends(get_import_service),
):
    record = await service.repo.get_by_id(import_id)
    if not record:
        return Response.error(code=404, msg="Import record not found")

    if record.created_by_id != current_user.id:
        return Response.error(code=403, msg="Access denied")

    if record.status not in [
        ImportStatus.PENDING,
        ImportStatus.PROCESSING,
    ]:
        return Response.error(code=400, msg="Cannot cancel this import")

    await service.cancel_import(import_id)

    return Response.success(
        data=ImportCancelResponse(
            id=import_id,
            status="cancelled",
            message="Import cancelled successfully",
        )
    )
