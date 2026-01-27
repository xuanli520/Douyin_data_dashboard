from alibabacloud_captcha20230305.client import Client as CaptchaClient
from alibabacloud_captcha20230305 import models as captcha_models
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models

from src.config import Settings, get_settings


class AliyunCaptchaService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.captcha_settings = self.settings.captcha

    def create_client(self) -> CaptchaClient:
        config = open_api_models.Config(
            access_key_id=self.captcha_settings.access_key_id,
            access_key_secret=self.captcha_settings.access_key_secret,
        )
        config.endpoint = self.captcha_settings.endpoint
        return CaptchaClient(config)

    async def verify(self, captcha_verify_param: str) -> bool:
        if not captcha_verify_param:
            return False

        if not self.captcha_settings.enabled:
            return True

        client = self.create_client()

        request = captcha_models.VerifyIntelligentCaptchaRequest(
            scene_id=self.captcha_settings.scene_id,
            captcha_verify_param=captcha_verify_param,
        )

        try:
            response = client.verify_intelligent_captcha_with_options(
                request,
                util_models.RuntimeOptions(),
            )
            if response.body and response.body.result:
                return response.body.result.verify_result
            return False
        except Exception:
            return False


def get_captcha_service() -> AliyunCaptchaService:
    return AliyunCaptchaService()
