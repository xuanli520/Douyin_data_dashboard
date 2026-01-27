from src.auth.captcha import get_captcha_service
from src.main import app
from src.shared.errors import ErrorCode


class MockCaptchaService:
    def __init__(self, verify_result: bool = True, raise_exception: bool = False):
        self.verify_result = verify_result
        self.raise_exception = raise_exception

    async def verify(self, captcha_verify_param: str) -> bool:
        if self.raise_exception:
            raise Exception("Captcha service error")
        return self.verify_result


def override_captcha_service(verify_result: bool = True, raise_exception: bool = False):
    return MockCaptchaService(
        verify_result=verify_result, raise_exception=raise_exception
    )


async def test_login_captcha_missing(test_client, test_user):
    response = await test_client.post(
        "/auth/jwt/login",
        data={"username": "test@example.com", "password": "testpassword123"},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["code"] == ErrorCode.AUTH_INVALID_CREDENTIALS


async def test_login_captcha_invalid(test_client, test_user):
    app.dependency_overrides[get_captcha_service] = lambda: override_captcha_service(
        verify_result=False
    )

    try:
        response = await test_client.post(
            "/auth/jwt/login",
            data={
                "username": "test@example.com",
                "password": "testpassword123",
                "captchaVerifyParam": "invalid",
            },
        )

        assert response.status_code == 401
        data = response.json()
        assert data["msg"] == "Captcha verification failed"
        assert data["code"] == ErrorCode.AUTH_INVALID_CREDENTIALS
    finally:
        app.dependency_overrides.pop(get_captcha_service, None)


async def test_login_success_with_valid_captcha(test_client, test_user):
    app.dependency_overrides[get_captcha_service] = lambda: override_captcha_service(
        verify_result=True
    )

    try:
        response = await test_client.post(
            "/auth/jwt/login",
            data={
                "username": "test@example.com",
                "password": "testpassword123",
                "captchaVerifyParam": "valid_token",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "Bearer"
    finally:
        app.dependency_overrides.pop(get_captcha_service, None)


async def test_login_wrong_password_with_valid_captcha(test_client, test_user):
    app.dependency_overrides[get_captcha_service] = lambda: override_captcha_service(
        verify_result=True
    )

    try:
        response = await test_client.post(
            "/auth/jwt/login",
            data={
                "username": "test@example.com",
                "password": "wrongpassword",
                "captchaVerifyParam": "valid_token",
            },
        )

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == ErrorCode.AUTH_INVALID_CREDENTIALS
    finally:
        app.dependency_overrides.pop(get_captcha_service, None)


async def test_login_captcha_exception_failsafe(test_client, test_user):
    app.dependency_overrides[get_captcha_service] = lambda: override_captcha_service(
        raise_exception=True
    )

    try:
        response = await test_client.post(
            "/auth/jwt/login",
            data={
                "username": "test@example.com",
                "password": "testpassword123",
                "captchaVerifyParam": "token",
            },
        )

        assert response.status_code == 401
        data = response.json()
        assert data["msg"] == "Captcha verification failed"
    finally:
        app.dependency_overrides.pop(get_captcha_service, None)
