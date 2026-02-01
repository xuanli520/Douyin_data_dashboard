import time
from typing import Any, Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.cache import CacheProtocol, get_cache

router = APIRouter()


async def get_engine() -> AsyncEngine:
    from src.session import engine

    return engine


@router.get("/test-logging")
async def test_logging():
    """Test logging endpoint - for development only, should be disabled in production."""
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


async def check_database(
    engine: Annotated[AsyncEngine, Depends(get_engine)],
) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start) * 1000
        return {"status": "healthy", "latency_ms": round(latency, 2)}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"status": "unhealthy", "latency_ms": None, "error": str(e)}


async def check_redis(
    cache: Annotated[CacheProtocol, Depends(get_cache)],
) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        from src.cache.local import LocalCache

        if isinstance(cache, LocalCache):
            return {"status": "healthy", "latency_ms": 0.0}
        await cache.client.ping()
        latency = (time.perf_counter() - start) * 1000
        return {"status": "healthy", "latency_ms": round(latency, 2)}
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {"status": "unhealthy", "latency_ms": None, "error": str(e)}


@router.get("/health")
async def health_check(
    db_result: dict[str, Any] = Depends(check_database),
    redis_result: dict[str, Any] = Depends(check_redis),
) -> JSONResponse:
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

    return JSONResponse(
        content={
            "status": status,
            "components": components,
            "timestamp": time.time(),
        },
        status_code=status_code,
    )
