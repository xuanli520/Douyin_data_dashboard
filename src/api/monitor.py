from fastapi import APIRouter, Depends
from fastapi.responses import Response

from src.auth import current_user, User
from src.middleware.monitor import generate_metrics

router = APIRouter()


@router.get("/metrics")
async def metrics(current_user: User = Depends(current_user)) -> Response:
    return Response(content=generate_metrics(), media_type="text/plain")
