import re
import time

from prometheus_client import Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.config import get_settings

http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(
        0.005,
        0.01,
        0.025,
        0.05,
        0.075,
        0.1,
        0.25,
        0.5,
        0.75,
        1.0,
        2.5,
        5.0,
        7.5,
        10.0,
    ),
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests in progress",
    ["method", "endpoint"],
)

http_exceptions_total = Counter(
    "http_exceptions_total",
    "Total number of HTTP exceptions",
    ["method", "endpoint", "exception_type"],
)

PATH_PARAMETER_PATTERN = re.compile(r"/[0-9]+")


def normalize_path(path: str) -> str:
    return PATH_PARAMETER_PATTERN.sub("/{}", path)


class MonitorMiddleware(BaseHTTPMiddleware):
    SKIP_PATHS = ("/metrics", "/docs", "/redoc", "/openapi")

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        settings = get_settings()
        if not settings.monitor.enabled:
            return await call_next(request)

        if request.url.path.startswith(self.SKIP_PATHS):
            return await call_next(request)

        method = request.method
        path = normalize_path(request.url.path)

        http_requests_in_progress.labels(method=method, endpoint=path).inc()

        start_time = time.perf_counter()
        exception_type = None

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            exception_type = type(e).__name__
            http_exceptions_total.labels(
                method=method, endpoint=path, exception_type=exception_type
            ).inc()
            raise
        finally:
            duration = time.perf_counter() - start_time
            http_requests_in_progress.labels(method=method, endpoint=path).dec()
            http_request_duration_seconds.labels(method=method, endpoint=path).observe(
                duration
            )

        http_requests_total.labels(
            method=method, endpoint=path, status_code=str(status_code)
        ).inc()

        return response


def generate_metrics() -> bytes:
    return generate_latest()
