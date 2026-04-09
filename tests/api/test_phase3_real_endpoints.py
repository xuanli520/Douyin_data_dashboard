from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.auth.captcha import get_captcha_service
from src.cache import get_cache
from src.domains.shop_dashboard.repository import ShopDashboardRepository
from src.main import app

SEEDED_DATE_RANGE = "2026-03-01,2026-03-03"


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
@pytest.mark.parametrize(
    "path,expected_keys",
    [
        (
            f"/api/v1/experience/overview?shop_id=1001&date_range={SEEDED_DATE_RANGE}",
            {"shop_id", "date_range", "overall_score", "dimensions", "alerts"},
        ),
        (
            f"/api/v1/experience/trend?shop_id=1001&dimension=product&date_range={SEEDED_DATE_RANGE}",
            {"shop_id", "dimension", "date_range", "trend"},
        ),
        (
            f"/api/v1/experience/issues?shop_id=1001&dimension=all&status=all&date_range={SEEDED_DATE_RANGE}&page=1&size=20",
            {"items", "meta"},
        ),
        (
            f"/api/v1/experience/drilldown/product?shop_id=1001&date_range={SEEDED_DATE_RANGE}&page=1&size=20",
            {
                "shop_id",
                "dimension",
                "date_range",
                "category_score",
                "sub_metrics",
                "score_ranges",
                "formula",
                "trend",
                "issues",
            },
        ),
        (
            f"/api/v1/metrics/product?shop_id=1001&date_range={SEEDED_DATE_RANGE}&period=30d",
            {
                "shop_id",
                "metric_type",
                "period",
                "date_range",
                "category_score",
                "sub_metrics",
                "score_ranges",
                "formula",
                "trend",
            },
        ),
    ],
)
async def test_phase3_endpoints_return_real_contract(
    api_client,
    phase3_user,
    seeded_phase3_data,
    path: str,
    expected_keys: set[str],
):
    headers = await get_auth_headers(
        api_client, "phase3user@example.com", "phase3real123"
    )
    response = await api_client.get(path, headers=headers)
    assert response.status_code == 200

    payload = response.json()
    assert payload["code"] == 200
    assert payload["msg"] == "success"
    assert expected_keys <= payload["data"].keys()
    assert "mock" not in payload["data"]
    assert "expected_release" not in payload["data"]


@pytest.mark.asyncio
async def test_phase3_experience_and_metrics_use_seeded_rows(
    api_client,
    phase3_user,
    seeded_phase3_data,
):
    headers = await get_auth_headers(
        api_client, "phase3user@example.com", "phase3real123"
    )

    overview_resp = await api_client.get(
        f"/api/v1/experience/overview?shop_id=1001&date_range={SEEDED_DATE_RANGE}",
        headers=headers,
    )
    overview = overview_resp.json()["data"]
    assert overview["overall_score"] > 0
    assert len(overview["dimensions"]) == 4

    issues_resp = await api_client.get(
        f"/api/v1/experience/issues?shop_id=1001&dimension=all&status=all&date_range={SEEDED_DATE_RANGE}&page=1&size=20",
        headers=headers,
    )
    issues = issues_resp.json()["data"]
    assert issues["meta"]["total"] >= 2
    assert any(item["id"] == "issue_1" for item in issues["items"])

    metric_resp = await api_client.get(
        f"/api/v1/metrics/product?shop_id=1001&date_range={SEEDED_DATE_RANGE}&period=30d",
        headers=headers,
    )
    metric = metric_resp.json()["data"]
    assert metric["metric_type"] == "product"
    assert len(metric["sub_metrics"]) >= 1
