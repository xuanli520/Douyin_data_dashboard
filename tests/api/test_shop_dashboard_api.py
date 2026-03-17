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
        "/api/v1/auth/jwt/login",
        data={"username": email, "password": password, "captchaVerifyParam": "valid"},
    )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def permission_data(test_db):
    from fastapi_users.password import PasswordHelper

    from src.auth import User
    from src.auth.models import Permission, Role, RolePermission, UserRole

    password_helper = PasswordHelper()
    hashed_password = password_helper.hash("shops123")

    async with test_db() as session:
        result = await session.execute(select(Permission))
        perm_map = {p.code: p for p in result.scalars().all()}

        code = "shop:view"
        if code not in perm_map:
            perm = Permission(code=code, name=code, module="shop")
            session.add(perm)
            await session.commit()
            perm_map[code] = perm

        role_result = await session.execute(
            select(Role).where(Role.name == "shops_reader")
        )
        role = role_result.scalar_one_or_none()
        if not role:
            role = Role(name="shops_reader", description="Shops Reader")
            session.add(role)
            await session.commit()
            await session.refresh(role)

        user = User(
            username="shopsuser",
            email="shopsuser@example.com",
            hashed_password=hashed_password,
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        session.add(UserRole(user_id=user.id, role_id=role.id))
        session.add(RolePermission(role_id=role.id, permission_id=perm_map[code].id))
        await session.commit()
        yield user


@pytest.mark.asyncio
async def test_shops_query_only(api_client, permission_data, test_db):
    async with test_db() as session:
        repo = ShopDashboardRepository(session)
        metric_date = date(2026, 3, 2)
        await repo.upsert_score(
            shop_id="shop-1",
            metric_date=metric_date,
            total_score=4.8,
            product_score=4.7,
            logistics_score=4.9,
            service_score=4.8,
            shop_name="demo-shop",
            source="script",
        )
        await repo.replace_reviews(
            shop_id="shop-1",
            metric_date=metric_date,
            reviews=[
                {
                    "review_id": "r-1",
                    "content": "good",
                    "is_replied": True,
                    "source": "script",
                }
            ],
        )
        await repo.replace_violations(
            shop_id="shop-1",
            metric_date=metric_date,
            violations=[
                {
                    "violation_id": "v-1",
                    "violation_type": "A",
                    "description": "desc",
                    "score": 1,
                    "source": "script",
                }
            ],
        )
        await session.commit()

    auth_headers = await get_auth_headers(
        api_client,
        "shopsuser@example.com",
        "shops123",
    )

    query_resp = await api_client.get(
        "/api/v1/shops?shop_id=shop-1&start_date=2026-03-01&end_date=2026-03-03",
        headers=auth_headers,
    )
    assert query_resp.status_code == 200
    assert query_resp.json()["data"]["items"][0]["shop_id"] == "shop-1"
    assert query_resp.json()["data"]["items"][0]["shop_name"] == "demo-shop"


@pytest.mark.asyncio
async def test_shops_root_returns_all_shops(api_client, permission_data, test_db):
    async with test_db() as session:
        repo = ShopDashboardRepository(session)
        await repo.upsert_score(
            shop_id="shop-2",
            metric_date=date(2026, 3, 1),
            total_score=4.5,
            product_score=4.4,
            logistics_score=4.6,
            service_score=4.5,
            bad_behavior_score=0.0,
            shop_name="shop-two",
            source="script",
        )
        await repo.upsert_score(
            shop_id="shop-1",
            metric_date=date(2026, 3, 1),
            total_score=4.3,
            product_score=4.2,
            logistics_score=4.4,
            service_score=4.3,
            bad_behavior_score=0.0,
            shop_name="shop-one-old",
            source="script",
        )
        await repo.upsert_score(
            shop_id="shop-1",
            metric_date=date(2026, 3, 2),
            total_score=4.9,
            product_score=4.8,
            logistics_score=4.9,
            service_score=4.9,
            bad_behavior_score=0.0,
            shop_name="shop-one-new",
            source="script",
        )
        await session.commit()

    auth_headers = await get_auth_headers(
        api_client,
        "shopsuser@example.com",
        "shops123",
    )

    response = await api_client.get("/api/v1/shops", headers=auth_headers)
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [item["shop_id"] for item in items] == ["shop-1", "shop-2"]
    assert items[0]["shop_name"] == "shop-one-new"
    assert items[0]["metric_date"] == "2026-03-02"


@pytest.mark.asyncio
async def test_dashboard_related_endpoints_removed(api_client, permission_data):
    auth_headers = await get_auth_headers(
        api_client,
        "shopsuser@example.com",
        "shops123",
    )

    trigger_resp = await api_client.post(
        "/api/v1/shop-dashboard/batch-trigger",
        json={"items": [{"data_source_id": 1, "rule_id": 2}]},
        headers=auth_headers,
    )
    assert trigger_resp.status_code == 404

    status_resp = await api_client.get(
        "/api/v1/shop-dashboard/status/task-1",
        headers=auth_headers,
    )
    assert status_resp.status_code == 404

    dashboard_resp = await api_client.get(
        "/api/v1/dashboard/overview?shop_id=shop-1&date_range=30d",
        headers=auth_headers,
    )
    assert dashboard_resp.status_code == 404
