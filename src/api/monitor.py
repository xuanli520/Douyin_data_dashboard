from fastapi import APIRouter
from fastapi.responses import Response

from src.middleware.monitor import generate_metrics

router = APIRouter()


@router.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_metrics(), media_type="text/plain")
