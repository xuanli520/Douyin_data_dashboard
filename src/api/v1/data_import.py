import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import current_user, User
from src.cache import get_cache, CacheProtocol
from src.domains.data_import.enums import ImportStatus
from src.domains.data_import.service import ImportService
from src.domains.data_import.schemas import (
    ImportUploadResponse,
    FieldMappingRequest,
    ImportValidateResponse,
    ImportConfirmResponse,
    ImportHistoryResponse,
    ImportHistoryItem,
    ImportDetailResponse,
    ImportCancelResponse,
)
from src.responses.base import Response
from src.session import get_session


router = APIRouter(prefix="/data-import", tags=["data-import"])
MAX_FILE_SIZE = 100 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
}


def get_import_service(
    session: AsyncSession = Depends(get_session),
    cache: CacheProtocol = Depends(get_cache),
) -> ImportService:
    try:
        redis = cache if hasattr(cache, "set") and cache is not None else None
    except Exception:
        redis = None
    return ImportService(session=session, redis=redis)


@router.post("/upload", response_model=Response[ImportUploadResponse])
async def upload_file(
    file: UploadFile = File(...),
    data_source_id: int = Form(...),
    current_user: User = Depends(current_user),
    service: ImportService = Depends(get_import_service),
):
    upload_dir = Path("uploads/imports")
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = file.filename or "unknown"
    file_ext = Path(filename).suffix.lower()

    if file_ext not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. Allowed: {', '.join(ALLOWED_CONTENT_TYPES.keys())}",
        )

    unique_filename = f"{uuid.uuid4().hex}{file_ext}"
    file_path = upload_dir / unique_filename

    try:
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE // (1024 * 1024)}MB",
            )

        file_path.write_bytes(content)
        file_size = len(content)
    except HTTPException:
        raise
    except Exception as e:
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    batch_no = f"IMP-{uuid.uuid4().hex[:8].upper()}"

    file_type = "excel" if file_ext in (".xlsx", ".xls") else "csv"

    try:
        record = await service.upload_file(
            file_path=str(file_path),
            file_name=filename,
            file_size=file_size,
            file_type=file_type,
            data_source_id=data_source_id,
            user_id=current_user.id or 0,
            batch_no=batch_no,
        )
    except Exception as e:
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(
            status_code=500, detail=f"Failed to create import record: {str(e)}"
        )

    return Response.success(
        data=ImportUploadResponse(
            id=record.id or 0,
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
    record = await service.get_import_record(import_id)
    if not record:
        return Response.error(code=404, msg="Import record not found")

    if record.created_by_id != current_user.id:
        return Response.error(code=403, msg="Access denied")

    rows = await service.parse_file(import_id)

    preview = []
    for row in rows[:5]:
        limited_row = {}
        for key, value in row.items():
            if isinstance(value, str) and len(value) > 1000:
                limited_row[key] = value[:1000] + "..."
            else:
                limited_row[key] = value
        preview.append(limited_row)

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
    record = await service.get_import_record(import_id)
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
    data_type: str = Query(
        "order", description="Data type for validation (order, product, etc.)"
    ),
    current_user: User = Depends(current_user),
    service: ImportService = Depends(get_import_service),
):
    record = await service.get_import_record(import_id)
    if not record:
        return Response.error(code=404, msg="Import record not found")

    if record.created_by_id != current_user.id:
        return Response.error(code=403, msg="Access denied")

    if record.status not in [ImportStatus.PENDING, ImportStatus.VALIDATION_FAILED]:
        return Response.error(
            code=400, msg="Import cannot be validated in current status"
        )

    rows = await service.parse_file(import_id)
    results = await service.validate_data(import_id, rows, data_type)

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
    record = await service.get_import_record(import_id)
    if not record:
        return Response.error(code=404, msg="Import record not found")

    if record.created_by_id != current_user.id:
        return Response.error(code=403, msg="Access denied")

    if record.status not in [
        ImportStatus.PENDING,
        ImportStatus.VALIDATION_FAILED,
        ImportStatus.SUCCESS,
    ]:
        return Response.error(
            code=400, msg="Import cannot be confirmed in current status"
        )

    try:
        rows = await service.parse_file(import_id)
        result = await service.confirm_import(import_id, rows)
    except ValueError as e:
        return Response.error(code=400, msg=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if result.get("cancelled"):
        return Response.error(code=400, msg="Import was cancelled")

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
async def get_import_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(current_user),
    service: ImportService = Depends(get_import_service),
) -> Response[ImportHistoryResponse]:
    histories, total = await service.list_import_history(
        user_id=current_user.id or 0, page=page, size=page_size
    )

    items = [
        ImportHistoryItem(
            id=h["id"],
            file_name=h["file_name"],
            status=h["status"].value if hasattr(h["status"], "value") else h["status"],
            total_rows=h["total_rows"],
            success_rows=h["success_rows"],
            failed_rows=h["failed_rows"],
            created_at=h["created_at"],
        )
        for h in histories
    ]

    return Response.success(
        data=ImportHistoryResponse(
            items=items,
            total=total,
            page=page,
            size=page_size,
        )
    )


@router.get("/{import_id}", response_model=Response[ImportDetailResponse])
async def get_import_detail(
    import_id: int,
    current_user: User = Depends(current_user),
    service: ImportService = Depends(get_import_service),
):
    record = await service.get_import_record(import_id)
    if not record:
        return Response.error(code=404, msg="Import record not found")

    if record.created_by_id != current_user.id:
        return Response.error(code=403, msg="Access denied")

    return Response.success(
        data=ImportDetailResponse(
            id=record.id,
            file_name=record.file_name,
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
    record = await service.get_import_record(import_id)
    if not record:
        return Response.error(code=404, msg="Import record not found")

    if record.created_by_id != current_user.id:
        return Response.error(code=403, msg="Access denied")

    if record.status not in [
        ImportStatus.PENDING,
        ImportStatus.PROCESSING,
        ImportStatus.VALIDATION_FAILED,
    ]:
        return Response.error(
            code=400, msg="Import cannot be cancelled in current status"
        )

    await service.cancel_import(import_id)

    return Response.success(
        data=ImportCancelResponse(
            id=import_id, status="cancelled", message="Import cancelled successfully"
        )
    )


@router.get("/progress/{import_id}")
async def get_import_progress(
    import_id: int,
    current_user: User = Depends(current_user),
    service: ImportService = Depends(get_import_service),
):
    record = await service.get_import_record(import_id)
    if not record:
        return Response.error(code=404, msg="Import record not found")

    if record.created_by_id != current_user.id:
        return Response.error(code=403, msg="Access denied")

    progress = await service.get_progress(import_id)

    return Response.success(
        data={
            "progress": progress,
            "record": {
                "id": record.id,
                "status": record.status.value,
                "total_rows": record.total_rows,
                "success_rows": record.success_rows,
                "failed_rows": record.failed_rows,
            },
        }
    )
