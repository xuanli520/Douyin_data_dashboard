from datetime import date
from types import SimpleNamespace

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
    hashed_password = password_helper.hash("shopdashboard123")

    async with test_db() as session:
        result = await session.execute(select(Permission))
        perm_map = {p.code: p for p in result.scalars().all()}

        codes = {
            "shop_dashboard:trigger",
            "shop_dashboard:status",
            "shop_dashboard:query",
        }
        for code in codes:
            if code not in perm_map:
                perm = Permission(code=code, name=code, module="shop_dashboard")
                session.add(perm)
                await session.commit()
                perm_map[code] = perm

        role_result = await session.execute(
            select(Role).where(Role.name == "shop_dashboard_operator")
        )
        role = role_result.scalar_one_or_none()
        if not role:
            role = Role(
                name="shop_dashboard_operator", description="Shop Dashboard Operator"
            )
            session.add(role)
            await session.commit()
            await session.refresh(role)

        user = User(
            username="shopdashboard",
            email="shopdashboard@example.com",
            hashed_password=hashed_password,
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        session.add(UserRole(user_id=user.id, role_id=role.id))
        for code in codes:
            session.add(
                RolePermission(role_id=role.id, permission_id=perm_map[code].id)
            )
        await session.commit()
        yield user


@pytest.mark.asyncio
async def test_shop_dashboard_batch_trigger_status_query(
    api_client,
    permission_data,
    test_db,
    monkeypatch,
):
    from src.api.v1 import shop_dashboard as module

    push_calls: list[dict] = []

    def _fake_push(**kwargs):
        push_calls.append(kwargs)
        return SimpleNamespace(task_id=f"task-{len(push_calls)}")

    class _FakeRedis:
        def hgetall(self, key: str):
            if key == "douyin:task:status:task-1":
                return {"status": "STARTED", "task_name": "sync_shop_dashboard"}
            return {}

    monkeypatch.setattr(module.sync_shop_dashboard, "push", _fake_push, raising=False)
    monkeypatch.setattr(module, "_get_redis_client", lambda: _FakeRedis())

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
        "shopdashboard@example.com",
        "shopdashboard123",
    )

    trigger_resp = await api_client.post(
        "/api/v1/shop-dashboard/batch-trigger",
        json={"items": [{"data_source_id": 1, "rule_id": 2}]},
        headers=auth_headers,
    )
    assert trigger_resp.status_code == 200
    task_id = trigger_resp.json()["data"]["items"][0]["task_id"]

    status_resp = await api_client.get(
        f"/api/v1/shop-dashboard/status/{task_id}",
        headers=auth_headers,
    )
    assert status_resp.status_code == 200

    query_resp = await api_client.get(
        "/api/v1/shop-dashboard/query?shop_id=shop-1&start_date=2026-03-01&end_date=2026-03-03",
        headers=auth_headers,
    )
    assert query_resp.status_code == 200
    assert query_resp.json()["data"]["items"][0]["shop_id"] == "shop-1"
    assert push_calls[0]["triggered_by"] == permission_data.id
