from pydantic import Field
from pydantic_settings import BaseSettings


class CaptchaSettings(BaseSettings):
    access_key_id: str
    access_key_secret: str
    scene_id: str = Field(default="71tobb9u")
    endpoint: str = Field(default="captcha.cn-shanghai.aliyuncs.com")
    enabled: bool = Field(default=True)
