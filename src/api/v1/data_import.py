from typing import Any

from fastapi import APIRouter, Depends, UploadFile, File

from src.auth import current_user, User
from src.responses.base import Response

router = APIRouter(prefix="/data-import", tags=["data-import"])


@router.post("/upload", response_model=Response[dict[str, Any]])
async def upload_file(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
) -> Response[dict[str, Any]]:
    return Response.success(
        data={"upload_id": "test_upload_123", "file_name": file.filename}
    )


@router.post("/parse", response_model=Response[dict[str, Any]])
async def parse_file(
    data: dict[str, Any],
    user: User = Depends(current_user),
) -> Response[dict[str, Any]]:
    return Response.success(
        data={"parsed": True, "columns": ["col1", "col2"], "row_count": 10}
    )


@router.post("/validate", response_model=Response[dict[str, Any]])
async def validate_data(
    data: dict[str, Any],
    user: User = Depends(current_user),
) -> Response[dict[str, Any]]:
    return Response.success(data={"valid": True, "errors": []})


@router.post("/confirm", response_model=Response[dict[str, Any]])
async def confirm_import(
    data: dict[str, Any],
    user: User = Depends(current_user),
) -> Response[dict[str, Any]]:
    return Response.success(data={"import_id": "import_123", "status": "completed"})


@router.get("/history", response_model=Response[list[dict[str, Any]]])
async def get_import_history(
    user: User = Depends(current_user),
) -> Response[list[dict[str, Any]]]:
    return Response.success(data=[])
