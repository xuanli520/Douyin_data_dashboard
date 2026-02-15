import asyncio
import inspect
import logging
from functools import wraps
from typing import Any, Callable, Literal

from fastapi import Depends
from fastapi.responses import JSONResponse

from src.auth import User, current_user
from src.exceptions import (
    EndpointDeprecatedException,
    EndpointInDevelopmentException,
    EndpointPlannedException,
)
from src.responses.base import Response

logger = logging.getLogger(__name__)


def _get_mock(mock_data: dict | list | Callable[[], dict | list]) -> dict | list:
    try:
        return mock_data() if callable(mock_data) else mock_data
    except Exception as e:
        logger.warning("mock_data callable failed: %s", e)
        if callable(mock_data):
            sig = inspect.signature(mock_data)
            if sig.return_annotation is list:
                return []
            return {}
        return {} if isinstance(mock_data, dict) else []


def _raise_in_development(
    data: dict | list | None,
    *,
    is_mock: bool,
    expected_release: str | None,
) -> None:
    raise EndpointInDevelopmentException(
        data=data,
        is_mock=is_mock,
        expected_release=expected_release,
    )


def in_development(
    mock_data: dict | list | Callable[[], dict | list],
    *,
    expected_release: str | None = None,
    prefer_real: bool = False,
    fallback_on_exception: bool = False,
):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            if not prefer_real:
                _raise_in_development(
                    _get_mock(mock_data),
                    is_mock=True,
                    expected_release=expected_release,
                )

            try:
                result = await func(*args, **kwargs)
                _raise_in_development(
                    result,
                    is_mock=False,
                    expected_release=expected_release,
                )
            except EndpointInDevelopmentException:
                raise
            except Exception as e:
                if fallback_on_exception:
                    logger.warning(
                        "in_development fallback: %s, error: %s",
                        func.__name__,
                        e,
                        exc_info=True,
                    )
                    _raise_in_development(
                        _get_mock(mock_data),
                        is_mock=True,
                        expected_release=expected_release,
                    )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            if not prefer_real:
                _raise_in_development(
                    _get_mock(mock_data),
                    is_mock=True,
                    expected_release=expected_release,
                )

            try:
                result = func(*args, **kwargs)
                _raise_in_development(
                    result,
                    is_mock=False,
                    expected_release=expected_release,
                )
            except EndpointInDevelopmentException:
                raise
            except Exception as e:
                if fallback_on_exception:
                    logger.warning(
                        "in_development fallback: %s, error: %s",
                        func.__name__,
                        e,
                        exc_info=True,
                    )
                    _raise_in_development(
                        _get_mock(mock_data),
                        is_mock=True,
                        expected_release=expected_release,
                    )
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def planned(
    expected_release: str | None = None,
):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(
            *args,
            _planned_user: User = Depends(current_user),
            **kwargs,
        ) -> Any:
            raise EndpointPlannedException(expected_release=expected_release)

        @wraps(func)
        def sync_wrapper(
            *args,
            _planned_user: User = Depends(current_user),
            **kwargs,
        ) -> Any:
            raise EndpointPlannedException(expected_release=expected_release)

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def deprecated(
    alternative: str | None = None,
    *,
    removal_date: str | None = None,
    mode: Literal["soft", "strict"] = "soft",
):
    def decorator(func: Callable) -> Callable:
        if mode == "strict":

            @wraps(func)
            async def async_wrapper_strict(
                *args,
                _deprecated_user: User = Depends(current_user),
                **kwargs,
            ) -> Any:
                raise EndpointDeprecatedException(
                    alternative=alternative, removal_date=removal_date
                )

            @wraps(func)
            def sync_wrapper_strict(
                *args,
                _deprecated_user: User = Depends(current_user),
                **kwargs,
            ) -> Any:
                raise EndpointDeprecatedException(
                    alternative=alternative, removal_date=removal_date
                )

            return (
                async_wrapper_strict
                if asyncio.iscoroutinefunction(func)
                else sync_wrapper_strict
            )

        @wraps(func)
        async def async_wrapper_soft(*args, **kwargs) -> Any:
            result = await func(*args, **kwargs)

            headers = {
                "X-Deprecated": "true",
                **({"X-Deprecated-Alternative": alternative} if alternative else {}),
                **({"X-Deprecated-Removal-Date": removal_date} if removal_date else {}),
            }

            if hasattr(result, "headers"):
                for k, v in headers.items():
                    result.headers[k] = v
                return result

            return JSONResponse(
                content=Response.success(data=result).model_dump(),
                status_code=200,
                headers=headers,
            )

        @wraps(func)
        def sync_wrapper_soft(*args, **kwargs) -> Any:
            result = func(*args, **kwargs)

            headers = {
                "X-Deprecated": "true",
                **({"X-Deprecated-Alternative": alternative} if alternative else {}),
                **({"X-Deprecated-Removal-Date": removal_date} if removal_date else {}),
            }

            if hasattr(result, "headers"):
                for k, v in headers.items():
                    result.headers[k] = v
                return result

            return JSONResponse(
                content=Response.success(data=result).model_dump(),
                status_code=200,
                headers=headers,
            )

        return (
            async_wrapper_soft
            if asyncio.iscoroutinefunction(func)
            else sync_wrapper_soft
        )

    return decorator
