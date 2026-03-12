from datetime import UTC, date, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.auth.captcha import get_captcha_service
from src.cache import get_cache
from src.domains.experience.models import ExperienceIssueDaily, ExperienceMetricDaily
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
        "/api/v1/auth/jwt/login",
        data={"username": email, "password": password, "captchaVerifyParam": "valid"},
    )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def phase3_user(test_db):
    from fastapi_users.password import PasswordHelper

    from src.auth import User
    from src.auth.models import Permission, Role, RolePermission, UserRole

    password_helper = PasswordHelper()
    hashed_password = password_helper.hash("phase3real123")
    permission_codes = ["experience:view", "metric:view", "dashboard:view"]

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
        rows: list[ExperienceMetricDaily] = []
        for metric_date, values in [
            (
                date(2026, 3, 1),
                {"product": 90.0, "logistics": 88.0, "service": 86.0, "risk": 80.0},
            ),
            (
                date(2026, 3, 2),
                {"product": 91.0, "logistics": 87.0, "service": 87.0, "risk": 81.0},
            ),
            (
                date(2026, 3, 3),
                {"product": 92.0, "logistics": 89.0, "service": 88.0, "risk": 79.0},
            ),
        ]:
            for dimension, score in values.items():
                rows.append(
                    ExperienceMetricDaily(
                        shop_id="1001",
                        metric_date=metric_date,
                        dimension=dimension,
                        metric_key="dimension_score",
                        metric_score=score,
                        metric_value=score,
                        metric_unit="pt",
                        source_field=f"raw.{dimension}.score",
                        formula_expr="normalized_dimension_score",
                        is_penalty=dimension == "risk",
                        deduct_points=max(0.0, 100.0 - score)
                        if dimension == "risk"
                        else 0.0,
                        source="seed",
                    )
                )

        rows.extend(
            [
                ExperienceMetricDaily(
                    shop_id="1001",
                    metric_date=date(2026, 3, 3),
                    dimension="product",
                    metric_key="product_quality_score",
                    metric_score=93.0,
                    metric_value=93.0,
                    metric_unit="pt",
                    source_field="raw.product.quality_score",
                    formula_expr="quality_feedback_weighted",
                    is_penalty=False,
                    deduct_points=0.0,
                    source="seed",
                ),
                ExperienceMetricDaily(
                    shop_id="1001",
                    metric_date=date(2026, 3, 3),
                    dimension="product",
                    metric_key="product_return_rate",
                    metric_score=89.0,
                    metric_value=1.8,
                    metric_unit="%",
                    source_field="raw.product.return_rate",
                    formula_expr="returns/orders*100",
                    is_penalty=False,
                    deduct_points=0.0,
                    source="seed",
                ),
                ExperienceMetricDaily(
                    shop_id="1001",
                    metric_date=date(2026, 3, 3),
                    dimension="product",
                    metric_key="product_negative_review_rate",
                    metric_score=87.0,
                    metric_value=2.4,
                    metric_unit="%",
                    source_field="raw.product.negative_review_rate",
                    formula_expr="negative_reviews/reviews*100",
                    is_penalty=False,
                    deduct_points=0.0,
                    source="seed",
                ),
            ]
        )

        session.add_all(rows)
        session.add_all(
            [
                ExperienceIssueDaily(
                    shop_id="1001",
                    metric_date=date(2026, 3, 3),
                    dimension="product",
                    issue_key="issue_1",
                    issue_title="product defect complaints",
                    status="pending",
                    owner="owner_1",
                    impact_score=18.5,
                    deduct_points=6.2,
                    occurred_at=datetime(2026, 3, 3, 9, 0, tzinfo=UTC),
                    deadline_at=datetime(2026, 3, 6, 18, 0, tzinfo=UTC),
                    source="seed",
                ),
                ExperienceIssueDaily(
                    shop_id="1001",
                    metric_date=date(2026, 3, 2),
                    dimension="risk",
                    issue_key="issue_2",
                    issue_title="policy violation warning",
                    status="resolved",
                    owner="owner_2",
                    impact_score=11.0,
                    deduct_points=3.0,
                    occurred_at=datetime(2026, 3, 2, 8, 0, tzinfo=UTC),
                    deadline_at=None,
                    source="seed",
                ),
            ]
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

    dashboard_response = await api_client.get(
        "/api/v1/dashboard/overview?shop_id=1001&date_range=30d",
        headers=headers,
    )
    assert dashboard_response.status_code == 200
    dashboard_payload = dashboard_response.json()
    assert dashboard_payload["code"] == 200
    assert dashboard_payload["msg"] == "success"
    assert "cards" in dashboard_payload["data"]


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
