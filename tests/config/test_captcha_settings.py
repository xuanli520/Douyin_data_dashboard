import pytest
from pydantic import ValidationError

from src.config.captcha import CaptchaSettings


class TestCaptchaSettings:
    def test_default_values(self):
        settings = CaptchaSettings(
            access_key_id="test_id",
            access_key_secret="test_secret",
        )

        assert settings.scene_id == "71tobb9u"
        assert settings.endpoint == "captcha.cn-shanghai.aliyuncs.com"
        assert settings.enabled is True

    def test_custom_values(self):
        settings = CaptchaSettings(
            access_key_id="custom_id",
            access_key_secret="custom_secret",
            scene_id="custom_scene",
            endpoint="custom.endpoint.com",
            enabled=False,
        )

        assert settings.access_key_id == "custom_id"
        assert settings.access_key_secret == "custom_secret"
        assert settings.scene_id == "custom_scene"
        assert settings.endpoint == "custom.endpoint.com"
        assert settings.enabled is False

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            CaptchaSettings()
