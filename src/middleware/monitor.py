import re
import time

from prometheus_client import Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.config import get_settings

monitor_settings = get_settings().monitor

http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=monitor_settings.buckets,
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

shop_dashboard_collection_total = Counter(
    "shop_dashboard_collection_total",
    "Shop dashboard collection task total",
    [
        "source",
        "status",
        "shop_mode",
        "shop_resolve_source",
        "bootstrap_status",
        "circuit_break_status",
    ],
)

shop_dashboard_collection_duration_seconds = Histogram(
    "shop_dashboard_collection_duration_seconds",
    "Shop dashboard collection task duration in seconds",
    [
        "source",
        "status",
        "shop_mode",
        "shop_resolve_source",
        "bootstrap_status",
        "circuit_break_status",
    ],
)

PATH_PARAMETER_PATTERN = re.compile(r"/(?:\d+|[0-9a-fA-F-]{36})")


def normalize_path(path: str) -> str:
    return PATH_PARAMETER_PATTERN.sub("/{}", path)


def observe_shop_dashboard_collection(
    *,
    source: str,
    status: str,
    duration_seconds: float,
    shop_mode: str = "unknown",
    shop_resolve_source: str = "unknown",
    bootstrap_status: str = "unknown",
    circuit_break_status: str = "unknown",
) -> None:
    safe_source = source if source else "unknown"
    safe_status = status if status else "unknown"
    safe_shop_mode = shop_mode if shop_mode else "unknown"
    safe_shop_resolve_source = shop_resolve_source if shop_resolve_source else "unknown"
    safe_bootstrap_status = bootstrap_status if bootstrap_status else "unknown"
    safe_circuit_break_status = (
        circuit_break_status if circuit_break_status else "unknown"
    )
    shop_dashboard_collection_total.labels(
        source=safe_source,
        status=safe_status,
        shop_mode=safe_shop_mode,
        shop_resolve_source=safe_shop_resolve_source,
        bootstrap_status=safe_bootstrap_status,
        circuit_break_status=safe_circuit_break_status,
    ).inc()
    shop_dashboard_collection_duration_seconds.labels(
        source=safe_source,
        status=safe_status,
        shop_mode=safe_shop_mode,
        shop_resolve_source=safe_shop_resolve_source,
        bootstrap_status=safe_bootstrap_status,
        circuit_break_status=safe_circuit_break_status,
    ).observe(max(duration_seconds, 0.0))


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
        status_code = None

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            exception_type = type(e).__name__
            http_exceptions_total.labels(
                method=method, endpoint=path, exception_type=exception_type
            ).inc()
            status_code = getattr(e, "status_code", 500)
            raise
        finally:
            duration = time.perf_counter() - start_time
            http_requests_in_progress.labels(method=method, endpoint=path).dec()
            http_request_duration_seconds.labels(method=method, endpoint=path).observe(
                duration
            )
            if status_code is not None:
                http_requests_total.labels(
                    method=method, endpoint=path, status_code=str(status_code)
                ).inc()

        return response


def generate_metrics() -> bytes:
    return generate_latest()
