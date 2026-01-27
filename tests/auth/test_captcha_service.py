import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.auth.captcha import AliyunCaptchaService


class MockCaptchaResult:
    def __init__(self, verify_result: bool):
        self.verify_result = verify_result


class MockResponseBody:
    def __init__(self, verify_result: bool | None):
        if verify_result is None:
            self.result = None
        else:
            self.result = MockCaptchaResult(verify_result)


class MockResponse:
    def __init__(self, verify_result: bool):
        self.body = MockResponseBody(verify_result)


class MockCaptchaSettings:
    def __init__(
        self,
        access_key_id: str = "test_access_key",
        access_key_secret: str = "test_secret",
        scene_id: str = "test_scene",
        endpoint: str = "captcha.cn-shanghai.aliyuncs.com",
        enabled: bool = True,
    ):
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.scene_id = scene_id
        self.endpoint = endpoint
        self.enabled = enabled


class MockSettings:
    def __init__(self, captcha_settings: MockCaptchaSettings | None = None):
        self.captcha = captcha_settings or MockCaptchaSettings()


@pytest.fixture
def mock_settings():
    return MockSettings()


@pytest.fixture
def captcha_service(mock_settings):
    return AliyunCaptchaService(settings=mock_settings)


class TestAliyunCaptchaService:
    def test_create_client(self, captcha_service):
        client = captcha_service.create_client()
        assert client is not None

    @pytest.mark.asyncio
    async def test_verify_success(self, captcha_service):
        mock_result = MagicMock()
        mock_result.verify_result = True
        mock_body = MagicMock()
        mock_body.result = mock_result
        mock_response = MagicMock()
        mock_response.body = mock_body

        with patch.object(captcha_service, "create_client") as mock_create:
            mock_client = MagicMock()
            mock_client.verify_intelligent_captcha_with_options.return_value = (
                mock_response
            )
            mock_create.return_value = mock_client

            result = await captcha_service.verify("valid_token")

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_failure(self, captcha_service):
        async def mock_verify(*args, **kwargs):
            mock_body = MagicMock()
            mock_body.result.verify_result = False
            return mock_body

        mock_client = MagicMock()
        mock_client.verify_intelligent_captcha_with_options = mock_verify

        with patch("src.auth.captcha.CaptchaClient") as mock_captcha_client:
            mock_captcha_client.return_value = mock_client

            result = await captcha_service.verify("invalid_token")

        assert result is False

    @pytest.mark.asyncio
    async def test_verify_empty_param(self, captcha_service):
        result = await captcha_service.verify("")
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_none_param(self, captcha_service):
        result = await captcha_service.verify(None)
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_exception(self, captcha_service):
        with patch.object(captcha_service, "create_client") as mock_create:
            mock_client = AsyncMock()
            mock_client.verify_intelligent_captcha_with_options.side_effect = Exception(
                "API error"
            )
            mock_create.return_value = mock_client

            result = await captcha_service.verify("token")

        assert result is False

    @pytest.mark.asyncio
    async def test_verify_disabled(self, mock_settings):
        mock_settings.captcha.enabled = False
        service = AliyunCaptchaService(settings=mock_settings)

        result = await service.verify("any_token")

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_no_result_body(self, captcha_service):
        async def mock_verify(*args, **kwargs):
            mock_body = MagicMock()
            mock_body.result = None
            return mock_body

        mock_client = MagicMock()
        mock_client.verify_intelligent_captcha_with_options = mock_verify

        with patch("src.auth.captcha.CaptchaClient") as mock_captcha_client:
            mock_captcha_client.return_value = mock_client

            result = await captcha_service.verify("token")

        assert result is False
