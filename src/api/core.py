import time
from typing import Any

from fastapi import APIRouter, Response
from loguru import logger
from sqlalchemy import text

from src.cache import cache
from src.session import engine

router = APIRouter()


@router.get("/test-logging")
async def test_logging():
    logger.info("Application logger test")
    logger.bind(action="test", resource_type="logging", result="success").info(
        "Audit logger test"
    )

    return {"message": "Check logs for output"}


@router.get("/test-logging-error")
async def test_logging_error():
    try:
        raise ValueError("Intentional test error")
    except ValueError:
        logger.exception("Exception logged with traceback")
        return {"message": "Exception logged, check logs"}


async def check_database() -> dict[str, Any]:
    start = time.perf_counter()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start) * 1000
        return {"status": "healthy", "latency_ms": round(latency, 2)}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"status": "unhealthy", "latency_ms": None, "error": str(e)}


async def check_redis() -> dict[str, Any]:
    start = time.perf_counter()
    try:
        await cache.client.ping()
        latency = (time.perf_counter() - start) * 1000
        return {"status": "healthy", "latency_ms": round(latency, 2)}
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {"status": "unhealthy", "latency_ms": None, "error": str(e)}


@router.get("/health")
async def health_check() -> Response:
    db_result = await check_database()
    redis_result = await check_redis()

    components = {"database": db_result, "redis": redis_result}

    if all(c["status"] == "healthy" for c in components.values()):
        status = "healthy"
        status_code = 200
    elif any(c["status"] == "healthy" for c in components.values()):
        status = "degraded"
        status_code = 200
    else:
        status = "unhealthy"
        status_code = 503

    return Response(
        content={
            "status": status,
            "components": components,
            "timestamp": time.time(),
        },
        status_code=status_code,
    )
