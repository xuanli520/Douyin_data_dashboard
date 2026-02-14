import pytest

from src.core.endpoint_status import in_development, planned, deprecated
from src.exceptions import (
    EndpointInDevelopmentException,
    EndpointPlannedException,
    EndpointDeprecatedException,
)


class TestInDevelopment:
    def test_returns_mock_data_by_default(self):
        @in_development(mock_data={"key": "value"})
        def sync_func():
            return {"real": "data"}

        with pytest.raises(EndpointInDevelopmentException) as exc_info:
            sync_func()

        assert exc_info.value.data["mock"] is True
        assert exc_info.value.data["data"] == {"key": "value"}

    def test_mock_data_from_callable(self):
        @in_development(mock_data=lambda: {"dynamic": "data"})
        def sync_func():
            return {"real": "data"}

        with pytest.raises(EndpointInDevelopmentException) as exc_info:
            sync_func()

        assert exc_info.value.data["data"] == {"dynamic": "data"}

    def test_mock_data_callable_exception_returns_empty(self):
        def failing_callable():
            raise RuntimeError("fail")

        @in_development(mock_data=failing_callable)
        def sync_func():
            return {"real": "data"}

        with pytest.raises(EndpointInDevelopmentException) as exc_info:
            sync_func()

        assert exc_info.value.data["data"] == {}

    def test_mock_data_callable_exception_returns_list_for_list_type(self):
        def failing_list_callable() -> list:
            raise RuntimeError("fail")

        @in_development(mock_data=failing_list_callable)
        def sync_func():
            return {"real": "data"}

        with pytest.raises(EndpointInDevelopmentException) as exc_info:
            sync_func()

        assert exc_info.value.data["data"] == []

    def test_mock_data_callable_exception_returns_dict_for_dict_type(self):
        def failing_dict_callable() -> dict:
            raise RuntimeError("fail")

        @in_development(mock_data=failing_dict_callable)
        def sync_func():
            return [{"real": "data"}]

        with pytest.raises(EndpointInDevelopmentException) as exc_info:
            sync_func()

        assert exc_info.value.data["data"] == {}

    def test_prefer_real_returns_real_data(self):
        @in_development(mock_data={"mock": "data"}, prefer_real=True)
        def sync_func():
            return {"real": "data"}

        with pytest.raises(EndpointInDevelopmentException) as exc_info:
            sync_func()

        assert exc_info.value.data["mock"] is False
        assert exc_info.value.data["data"] == {"real": "data"}

    def test_prefer_real_raises_original_exception(self):
        @in_development(mock_data={"mock": "data"}, prefer_real=True)
        def failing_func():
            raise ValueError("original error")

        with pytest.raises(ValueError, match="original error"):
            failing_func()

    def test_fallback_on_exception_returns_mock_on_error(self):
        @in_development(
            mock_data={"fallback": "data"},
            prefer_real=True,
            fallback_on_exception=True,
        )
        def failing_func():
            raise ValueError("original error")

        with pytest.raises(EndpointInDevelopmentException) as exc_info:
            failing_func()

        assert exc_info.value.data["mock"] is True
        assert exc_info.value.data["data"] == {"fallback": "data"}

    def test_expected_release_included(self):
        @in_development(mock_data={"key": "value"}, expected_release="2026-03-01")
        def sync_func():
            pass

        with pytest.raises(EndpointInDevelopmentException) as exc_info:
            sync_func()

        assert exc_info.value.data["expected_release"] == "2026-03-01"

    def test_mock_data_list(self):
        @in_development(mock_data=[{"id": 1}, {"id": 2}])
        def sync_func():
            return [{"real": "data"}]

        with pytest.raises(EndpointInDevelopmentException) as exc_info:
            sync_func()

        assert exc_info.value.data["data"] == [{"id": 1}, {"id": 2}]

    def test_mock_data_list_from_callable(self):
        @in_development(mock_data=lambda: [{"id": 1}, {"id": 2}])
        def sync_func():
            return [{"real": "data"}]

        with pytest.raises(EndpointInDevelopmentException) as exc_info:
            sync_func()

        assert exc_info.value.data["data"] == [{"id": 1}, {"id": 2}]

    @pytest.mark.asyncio
    async def test_async_mock_data_list(self):
        @in_development(mock_data=[{"id": 1}, {"id": 2}])
        async def async_func():
            return [{"real": "data"}]

        with pytest.raises(EndpointInDevelopmentException) as exc_info:
            await async_func()

        assert exc_info.value.data["data"] == [{"id": 1}, {"id": 2}]

    @pytest.mark.asyncio
    async def test_async_returns_mock_data_by_default(self):
        @in_development(mock_data={"async": "mock"})
        async def async_func():
            return {"real": "data"}

        with pytest.raises(EndpointInDevelopmentException) as exc_info:
            await async_func()

        assert exc_info.value.data["mock"] is True
        assert exc_info.value.data["data"] == {"async": "mock"}

    @pytest.mark.asyncio
    async def test_async_prefer_real_returns_real_data(self):
        @in_development(mock_data={"mock": "data"}, prefer_real=True)
        async def async_func():
            return {"async": "real"}

        with pytest.raises(EndpointInDevelopmentException) as exc_info:
            await async_func()

        assert exc_info.value.data["mock"] is False
        assert exc_info.value.data["data"] == {"async": "real"}

    @pytest.mark.asyncio
    async def test_async_fallback_on_exception(self):
        @in_development(
            mock_data={"fallback": "data"},
            prefer_real=True,
            fallback_on_exception=True,
        )
        async def failing_async():
            raise ValueError("async error")

        with pytest.raises(EndpointInDevelopmentException) as exc_info:
            await failing_async()

        assert exc_info.value.data["mock"] is True


class TestPlanned:
    def test_raises_endpoint_planned_exception(self):
        @planned()
        def sync_func():
            return "never reached"

        with pytest.raises(EndpointPlannedException) as exc_info:
            sync_func()

        assert exc_info.value.code.value == 70002

    def test_includes_expected_release(self):
        @planned(expected_release="2026-04-01")
        def sync_func():
            pass

        with pytest.raises(EndpointPlannedException) as exc_info:
            sync_func()

        assert exc_info.value.data == {"expected_release": "2026-04-01"}

    @pytest.mark.asyncio
    async def test_async_raises_endpoint_planned_exception(self):
        @planned()
        async def async_func():
            return "never reached"

        with pytest.raises(EndpointPlannedException) as exc_info:
            await async_func()

        assert exc_info.value.code.value == 70002


class TestDeprecatedSoft:
    def test_soft_mode_returns_json_response_with_headers(self):
        @deprecated(alternative="/api/v2/new")
        def sync_func():
            return {"data": "value"}

        result = sync_func()

        assert result.status_code == 200
        assert result.headers["X-Deprecated"] == "true"
        assert result.headers["X-Deprecated-Alternative"] == "/api/v2/new"

    def test_soft_mode_includes_removal_date(self):
        @deprecated(removal_date="2026-06-01")
        def sync_func():
            return {"data": "value"}

        result = sync_func()

        assert result.headers["X-Deprecated-Removal-Date"] == "2026-06-01"

    def test_soft_mode_no_alternative_no_header(self):
        @deprecated()
        def sync_func():
            return {"data": "value"}

        result = sync_func()

        assert result.headers["X-Deprecated"] == "true"
        assert "X-Deprecated-Alternative" not in result.headers

    def test_soft_mode_preserves_existing_response_headers(self):
        from fastapi.responses import JSONResponse

        @deprecated(alternative="/api/v2/new")
        def sync_func():
            return JSONResponse(
                content={"data": "value"}, status_code=200, headers={"X-Custom": "test"}
            )

        result = sync_func()

        assert result.headers["X-Custom"] == "test"
        assert result.headers["X-Deprecated"] == "true"

    @pytest.mark.asyncio
    async def test_async_soft_mode_returns_json_response_with_headers(self):
        @deprecated(alternative="/api/v2/new")
        async def async_func():
            return {"async": "data"}

        result = await async_func()

        assert result.status_code == 200
        assert result.headers["X-Deprecated"] == "true"


class TestDeprecatedStrict:
    def test_strict_mode_raises_exception(self):
        @deprecated(mode="strict", alternative="/api/v2/new")
        def sync_func():
            return "never reached"

        with pytest.raises(EndpointDeprecatedException) as exc_info:
            sync_func()

        assert exc_info.value.code.value == 70003
        assert exc_info.value.data["alternative"] == "/api/v2/new"

    def test_strict_mode_includes_removal_date(self):
        @deprecated(mode="strict", removal_date="2026-06-01")
        def sync_func():
            pass

        with pytest.raises(EndpointDeprecatedException) as exc_info:
            sync_func()

        assert exc_info.value.data["removal_date"] == "2026-06-01"

    def test_strict_mode_no_alternative_no_data(self):
        @deprecated(mode="strict")
        def sync_func():
            pass

        with pytest.raises(EndpointDeprecatedException) as exc_info:
            sync_func()

        assert exc_info.value.data is None

    @pytest.mark.asyncio
    async def test_async_strict_mode_raises_exception(self):
        @deprecated(mode="strict", alternative="/api/v2/new")
        async def async_func():
            return "never reached"

        with pytest.raises(EndpointDeprecatedException) as exc_info:
            await async_func()

        assert exc_info.value.code.value == 70003


class TestExceptionProperties:
    def test_in_development_exception_structure(self):
        exc = EndpointInDevelopmentException(
            data={"test": "data"}, is_mock=True, expected_release="2026-03-01"
        )

        assert exc.code.value == 70001
        assert exc.msg == "该功能正在开发中，当前返回演示数据"
        assert exc.data["mock"] is True
        assert exc.data["expected_release"] == "2026-03-01"
        assert exc.data["data"] == {"test": "data"}

    def test_planned_exception_structure(self):
        exc = EndpointPlannedException(expected_release="2026-04-01")

        assert exc.code.value == 70002
        assert exc.msg == "该功能正在规划中，暂未实现"
        assert exc.data == {"expected_release": "2026-04-01"}

    def test_planned_exception_no_release(self):
        exc = EndpointPlannedException()

        assert exc.data is None

    def test_deprecated_exception_structure(self):
        exc = EndpointDeprecatedException(
            alternative="/api/v2/new", removal_date="2026-06-01"
        )

        assert exc.code.value == 70003
        assert exc.msg == "该接口已弃用，请迁移到新接口"
        assert exc.data["alternative"] == "/api/v2/new"
        assert exc.data["removal_date"] == "2026-06-01"

    def test_deprecated_exception_no_params(self):
        exc = EndpointDeprecatedException()

        assert exc.data is None
