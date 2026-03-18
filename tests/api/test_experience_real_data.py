from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.auth.captcha import get_captcha_service
from src.cache import get_cache
from src.domains.shop_dashboard.repository import ShopDashboardRepository
from src.main import app


class MockCaptchaService:
    async def verify(self, captcha_verify_param: str) -> bool:
        return True


@pytest.fixture
async def api_client(test_db, local_cache):
    async def override_get_cache():
        yield local_cache

    app.dependency_overrides[get_cache] = override_get_cache
    app.dependency_overrides[get_captcha_service] = lambda: MockCaptchaService()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.pop(get_cache, None)
    app.dependency_overrides.pop(get_captcha_service, None)


async def get_auth_headers(client: AsyncClient, email: str, password: str) -> dict:
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password, "captchaVerifyParam": "valid"},
    )
    token = response.cookies.get("access_token")
    assert token is not None
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def phase3_user(test_db):
    from fastapi_users.password import PasswordHelper

    from src.auth import User
    from src.auth.models import Permission, Role, RolePermission, UserRole

    password_helper = PasswordHelper()
    hashed_password = password_helper.hash("phase3real123")
    permission_codes = ["experience:view", "metric:view"]

    async with test_db() as session:
        result = await session.execute(select(Permission))
        perm_map = {perm.code: perm for perm in result.scalars().all()}
        for code in permission_codes:
            if code not in perm_map:
                module = code.split(":", 1)[0]
                permission = Permission(code=code, name=code, module=module)
                session.add(permission)
                await session.commit()
                perm_map[code] = permission

        role_result = await session.execute(select(Role).where(Role.name == "phase3"))
        role = role_result.scalar_one_or_none()
        if role is None:
            role = Role(name="phase3", description="phase3 real endpoint role")
            session.add(role)
            await session.commit()
            await session.refresh(role)

        user = User(
            username="phase3user",
            email="phase3user@example.com",
            hashed_password=hashed_password,
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        session.add(UserRole(user_id=user.id, role_id=role.id))
        for code in permission_codes:
            session.add(
                RolePermission(role_id=role.id, permission_id=perm_map[code].id)
            )
        await session.commit()
        yield user


@pytest.fixture
async def seeded_phase3_data(test_db):
    async with test_db() as session:
        repo = ShopDashboardRepository(session)
        for metric_date, values in [
            (
                date(2026, 3, 1),
                {
                    "total": 86.6,
                    "product": 90.0,
                    "logistics": 88.0,
                    "service": 86.0,
                    "bad_behavior": 20.0,
                },
            ),
            (
                date(2026, 3, 2),
                {
                    "total": 87.2,
                    "product": 91.0,
                    "logistics": 87.0,
                    "service": 87.0,
                    "bad_behavior": 19.0,
                },
            ),
            (
                date(2026, 3, 3),
                {
                    "total": 89.9,
                    "product": 92.0,
                    "logistics": 89.0,
                    "service": 88.0,
                    "bad_behavior": 21.0,
                },
            ),
        ]:
            await repo.upsert_score(
                shop_id="1001",
                metric_date=metric_date,
                total_score=values["total"],
                product_score=values["product"],
                logistics_score=values["logistics"],
                service_score=values["service"],
                bad_behavior_score=values["bad_behavior"],
                source="seed",
            )

        await repo.replace_violations(
            shop_id="1001",
            metric_date=date(2026, 3, 3),
            violations=[
                {
                    "violation_id": "issue_1",
                    "violation_type": "product",
                    "description": "product defect complaints",
                    "score": 6,
                    "source": "seed",
                }
            ],
        )
        await repo.replace_violations(
            shop_id="1001",
            metric_date=date(2026, 3, 2),
            violations=[
                {
                    "violation_id": "issue_2",
                    "violation_type": "risk",
                    "description": "policy violation warning",
                    "score": 3,
                    "source": "seed",
                }
            ],
        )
        await repo.upsert_cold_metrics(
            shop_id="1001",
            metric_date=date(2026, 3, 1),
            reason="cold reason fallback",
            violations_detail=[],
            arbitration_detail=[],
            dsr_trend=[],
            source="seed",
        )
        await session.commit()


@pytest.mark.asyncio
async def test_experience_real_data_success_contract(
    api_client,
    phase3_user,
    seeded_phase3_data,
):
    headers = await get_auth_headers(
        api_client,
        "phase3user@example.com",
        "phase3real123",
    )

    response = await api_client.get(
        "/api/v1/experience/overview?shop_id=1001&date_range=30d",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["msg"] == "success"
    assert payload["data"]["shop_id"] == 1001
    assert "mock" not in payload["data"]

    metric_response = await api_client.get(
        "/api/v1/metrics/product?shop_id=1001&date_range=30d&period=30d",
        headers=headers,
    )
    assert metric_response.status_code == 200
    metric_payload = metric_response.json()
    assert metric_payload["code"] == 200
    assert metric_payload["msg"] == "success"
    assert metric_payload["data"]["metric_type"] == "product"


@pytest.mark.asyncio
async def test_experience_real_data_empty_dataset_should_return_empty_structures(
    api_client,
    phase3_user,
):
    headers = await get_auth_headers(
        api_client,
        "phase3user@example.com",
        "phase3real123",
    )

    trend_response = await api_client.get(
        "/api/v1/experience/trend?shop_id=1001&dimension=product&date_range=30d",
        headers=headers,
    )
    assert trend_response.status_code == 200
    trend_payload = trend_response.json()
    assert trend_payload["code"] == 200
    assert trend_payload["data"]["trend"] == []

    issues_response = await api_client.get(
        "/api/v1/experience/issues?shop_id=1001&dimension=all&status=all&date_range=30d&page=1&size=20",
        headers=headers,
    )
    assert issues_response.status_code == 200
    issues_payload = issues_response.json()
    assert issues_payload["code"] == 200
    assert issues_payload["data"]["items"] == []
    assert issues_payload["data"]["meta"]["total"] == 0


@pytest.mark.asyncio
async def test_experience_real_data_issue_filters_should_work(
    api_client,
    phase3_user,
    seeded_phase3_data,
):
    headers = await get_auth_headers(
        api_client,
        "phase3user@example.com",
        "phase3real123",
    )
    response = await api_client.get(
        "/api/v1/experience/issues?shop_id=1001&dimension=product&status=pending&date_range=30d&page=1&size=20",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["meta"]["total"] >= 1
    assert all(item["dimension"] == "product" for item in payload["data"]["items"])
    assert all(item["status"] == "pending" for item in payload["data"]["items"])


@pytest.mark.asyncio
async def test_experience_real_data_invalid_pagination_should_return_422(
    api_client,
    phase3_user,
):
    headers = await get_auth_headers(
        api_client,
        "phase3user@example.com",
        "phase3real123",
    )
    response = await api_client.get(
        "/api/v1/experience/issues?shop_id=1001&dimension=all&status=all&date_range=30d&page=0&size=20",
        headers=headers,
    )
    assert response.status_code == 422

    too_large_size = await api_client.get(
        "/api/v1/experience/issues?shop_id=1001&dimension=all&status=all&date_range=30d&page=1&size=999",
        headers=headers,
    )
    assert too_large_size.status_code == 422


@pytest.mark.asyncio
async def test_experience_real_data_too_large_date_range_should_return_422(
    api_client,
    phase3_user,
):
    headers = await get_auth_headers(
        api_client,
        "phase3user@example.com",
        "phase3real123",
    )
    response = await api_client.get(
        "/api/v1/experience/overview?shop_id=1001&date_range=999d",
        headers=headers,
    )
    assert response.status_code == 422
