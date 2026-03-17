from __future__ import annotations

from typing import Any

import httpx
import pytest

from src.config import get_settings
from src.scrapers.shop_dashboard import session_bootstrapper as module
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.scrapers.shop_dashboard.session_bootstrapper import SessionBootstrapper
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: Any = None,
        cookies: dict[str, str] | None = None,
    ):
        self.status_code = status_code
        self._payload = payload
        self.cookies = httpx.Cookies(cookies or {})

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _install_httpx_async_client(monkeypatch, events: dict[tuple[str, str], list[Any]]):
    call_log: list[tuple[str, str]] = []

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            _ = (args, kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            _ = (exc_type, exc, tb)
            return None

        async def get(self, path, params=None, headers=None):
            _ = (params, headers)
            return _dispatch("GET", str(path))

        async def post(self, path, params=None, headers=None, json=None):
            _ = (params, headers, json)
            return _dispatch("POST", str(path))

    def _dispatch(method: str, path: str):
        call_log.append((method, path))
        queue = events.get((method, path))
        if not queue:
            raise RuntimeError(f"missing_event:{method}:{path}")
        current = queue.pop(0)
        if isinstance(current, Exception):
            raise current
        if isinstance(current, dict):
            return _FakeResponse(
                status_code=int(current.get("status_code", 200)),
                payload=current.get("payload"),
                cookies=current.get("cookies"),
            )
        if isinstance(current, _FakeResponse):
            return current
        raise RuntimeError(f"unsupported_event:{method}:{path}")

    monkeypatch.setattr(module.httpx, "AsyncClient", _FakeAsyncClient)
    return call_log


def _build_runtime() -> ShopDashboardRuntimeConfig:
    return ShopDashboardRuntimeConfig(
        shop_mode="EXACT",
        resolved_shop_ids=["shop-a"],
        catalog_stale=False,
        shop_id="shop-a",
        cookies={"sid": "token"},
        proxy=None,
        timeout=15,
        retry_count=0,
        rate_limit=100,
        granularity="DAY",
        time_range={"start": "2026-03-01", "end": "2026-03-01"},
        incremental_mode="BY_DATE",
        backfill_last_n_days=1,
        data_latency="T+1",
        target_type="SHOP_OVERVIEW",
        metrics=["overview", "analysis"],
        dimensions=[],
        filters={"shop_id": ["shop-a"]},
        top_n=None,
        include_long_tail=False,
        session_level=False,
        dedupe_key=None,
        rule_id=7,
        execution_id="exec-bootstrap",
        fallback_chain=("http",),
        graphql_query=None,
        common_query={"msToken": "m1"},
        token_keys=[],
        api_groups=["overview", "analysis"],
        account_id="acct-1",
    )


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_bootstrap_fails_when_verify_actual_shop_id_mismatch(
    tmp_path, monkeypatch
):
    events = {
        ("GET", "/byteshop/loginv2/chooseshop"): [
            {"payload": {"code": 0, "data": {}}},
        ],
        (
            "GET",
            "/governance/shop/experiencescore/getOverviewByVersion",
        ): [
            {"payload": {"code": 0, "data": {"shop_id": "shop-a"}}},
        ],
        ("GET", "/governance/shop/experiencescore/getAnalysisScore"): [
            {"payload": {"code": 0, "data": {"shop_id": "shop-b"}}},
        ],
    }
    _install_httpx_async_client(monkeypatch, events)

    store = SessionStateStore(base_dir=tmp_path)
    bootstrapper = SessionBootstrapper(state_store=store)
    runtime = _build_runtime()

    result = await bootstrapper.bootstrap_shop(
        runtime=runtime,
        shop_id="shop-a",
        verify_metric_date="2026-03-01",
    )

    assert result["bootstrap_failed"] is True
    assert result["error_code"] == "verify_shop_mismatch"
    assert result["target_shop_id"] == "shop-a"
    assert result["actual_shop_id"] == "shop-b"
    assert store.load_bundle("acct-1", "shop-a") is None


@pytest.mark.asyncio
async def test_bootstrap_choose_shop_uses_fallback_when_primary_returns_10008(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SHOP_DASHBOARD__BOOTSTRAP_VERIFY_RETRY_LIMIT", "0")
    events = {
        ("GET", "/byteshop/loginv2/chooseshop"): [
            {
                "payload": {
                    "code": 10008,
                    "msg": "用户登录信息异常，请刷新或者重新登录后重试",
                }
            },
        ],
        ("GET", "/byteshop/index/chooseshop"): [
            {"payload": {"code": 0, "data": {}}},
        ],
        (
            "GET",
            "/governance/shop/experiencescore/getOverviewByVersion",
        ): [
            {"payload": {"code": 0, "data": {"shop_id": "shop-a"}}},
        ],
        ("GET", "/governance/shop/experiencescore/getAnalysisScore"): [
            {"payload": {"code": 0, "data": {"shop_id": "shop-a"}}},
        ],
    }
    call_log = _install_httpx_async_client(monkeypatch, events)

    store = SessionStateStore(base_dir=tmp_path)
    bootstrapper = SessionBootstrapper(state_store=store)
    runtime = _build_runtime()

    result = await bootstrapper.bootstrap_shop(
        runtime=runtime,
        shop_id="shop-a",
        verify_metric_date="2026-03-01",
    )

    assert result["bootstrap_failed"] is False
    assert result["status"] == "success"
    assert ("GET", "/byteshop/loginv2/chooseshop") in call_log
    assert ("GET", "/byteshop/index/chooseshop") in call_log


@pytest.mark.asyncio
async def test_bootstrap_choose_shop_propagates_set_cookie_to_bundle(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SHOP_DASHBOARD__BOOTSTRAP_VERIFY_RETRY_LIMIT", "0")

    events = {
        ("GET", "/byteshop/loginv2/chooseshop"): [
            {
                "payload": {
                    "code": 10008,
                    "msg": "用户登录信息异常，请刷新或者重新登录后重试",
                }
            },
        ],
        ("GET", "/byteshop/index/chooseshop"): [
            {
                "payload": {"code": 0, "data": {}},
                "cookies": {"PHPSESSID": "new-session-id"},
            },
        ],
        (
            "GET",
            "/governance/shop/experiencescore/getOverviewByVersion",
        ): [
            {"payload": {"code": 0, "data": {"shop_id": "shop-a"}}},
        ],
        ("GET", "/governance/shop/experiencescore/getAnalysisScore"): [
            {"payload": {"code": 0, "data": {"shop_id": "shop-a"}}},
        ],
    }
    _install_httpx_async_client(monkeypatch, events)

    store = SessionStateStore(base_dir=tmp_path)
    bootstrapper = SessionBootstrapper(state_store=store)
    runtime = _build_runtime()

    result = await bootstrapper.bootstrap_shop(
        runtime=runtime,
        shop_id="shop-a",
        verify_metric_date="2026-03-01",
    )

    assert result["bootstrap_failed"] is False
    bundle = store.load_bundle("acct-1", "shop-a")
    assert isinstance(bundle, dict)
    assert bundle["cookies"]["PHPSESSID"] == "new-session-id"


@pytest.mark.asyncio
async def test_bootstrap_fails_when_verify_request_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOP_DASHBOARD__BOOTSTRAP_VERIFY_RETRY_LIMIT", "0")
    events = {
        ("GET", "/byteshop/loginv2/chooseshop"): [
            {"payload": {"code": 0, "data": {}}},
        ],
        (
            "GET",
            "/governance/shop/experiencescore/getOverviewByVersion",
        ): [
            httpx.TimeoutException("timeout"),
        ],
    }
    _install_httpx_async_client(monkeypatch, events)

    store = SessionStateStore(base_dir=tmp_path)
    bootstrapper = SessionBootstrapper(state_store=store)
    runtime = _build_runtime()

    result = await bootstrapper.bootstrap_shop(
        runtime=runtime,
        shop_id="shop-a",
        verify_metric_date="2026-03-01",
    )

    assert result["bootstrap_failed"] is True
    assert result["error_code"] == "verify_request_failed"
    assert result["target_shop_id"] == "shop-a"
    assert store.load_bundle("acct-1", "shop-a") is None


@pytest.mark.asyncio
async def test_bootstrap_fails_when_verify_actual_shop_id_missing(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SHOP_DASHBOARD__BOOTSTRAP_VERIFY_RETRY_LIMIT", "0")
    events = {
        ("GET", "/byteshop/loginv2/chooseshop"): [
            {"payload": {"code": 0, "data": {}}},
        ],
        (
            "GET",
            "/governance/shop/experiencescore/getOverviewByVersion",
        ): [
            {"payload": {"code": 0, "data": {}}},
        ],
        ("GET", "/governance/shop/experiencescore/getAnalysisScore"): [
            {"payload": {"code": 0, "data": {}}},
        ],
    }
    _install_httpx_async_client(monkeypatch, events)

    store = SessionStateStore(base_dir=tmp_path)
    bootstrapper = SessionBootstrapper(state_store=store)
    runtime = _build_runtime()

    result = await bootstrapper.bootstrap_shop(
        runtime=runtime,
        shop_id="shop-a",
        verify_metric_date="2026-03-01",
    )

    assert result["bootstrap_failed"] is True
    assert result["error_code"] == "verify_request_failed"
    assert result["bootstrap_verify_error_code"] == "verify_request_failed"
    assert store.load_bundle("acct-1", "shop-a") is None


@pytest.mark.asyncio
async def test_bootstrap_invalidates_old_session_version_and_rebuilds(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("SHOP_DASHBOARD__BOOTSTRAP_BUNDLE_SESSION_VERSION", "2")
    monkeypatch.setenv("SHOP_DASHBOARD__BOOTSTRAP_VERIFY_RETRY_LIMIT", "0")
    events = {
        ("GET", "/byteshop/loginv2/chooseshop"): [
            {"payload": {"code": 0, "data": {}}},
        ],
        (
            "GET",
            "/governance/shop/experiencescore/getOverviewByVersion",
        ): [
            {"payload": {"code": 0, "data": {"shop_id": "shop-a"}}},
        ],
        ("GET", "/governance/shop/experiencescore/getAnalysisScore"): [
            {"payload": {"code": 0, "data": {"shop_id": "shop-a"}}},
        ],
    }
    call_log = _install_httpx_async_client(monkeypatch, events)

    store = SessionStateStore(base_dir=tmp_path)
    store.save_bundle(
        "acct-1",
        "shop-a",
        {
            "cookies": {"sid": "old"},
            "common_query": {"msToken": "old"},
            "validated_shop_id": "shop-a",
            "verified_actual_shop_id": "shop-a",
            "verify_status": "passed",
            "verified_at": "2026-03-10T00:00:00+00:00",
            "session_version": "1",
        },
    )

    bootstrapper = SessionBootstrapper(state_store=store)
    runtime = _build_runtime()

    result = await bootstrapper.bootstrap_shop(
        runtime=runtime,
        shop_id="shop-a",
        verify_metric_date="2026-03-01",
    )

    assert result["bootstrap_failed"] is False
    assert result["status"] == "success"
    bundle = store.load_bundle("acct-1", "shop-a")
    assert isinstance(bundle, dict)
    assert bundle["session_version"] == "2"
    assert bundle["verify_status"] == "passed"
    assert bundle["verified_actual_shop_id"] == "shop-a"
    assert ("GET", "/byteshop/loginv2/chooseshop") in call_log


@pytest.mark.asyncio
async def test_bootstrap_verify_reuses_response_set_cookie_across_retries(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("SHOP_DASHBOARD__BOOTSTRAP_VERIFY_RETRY_LIMIT", "1")
    cookie_log: list[tuple[str, str]] = []
    events = {
        ("GET", "/byteshop/loginv2/chooseshop"): [
            {"payload": {"code": 0, "data": {}}},
        ],
        (
            "GET",
            "/governance/shop/experiencescore/getOverviewByVersion",
        ): [
            {
                "payload": {"code": 500},
                "cookies": {"sid": "new-verify-token"},
            },
            {"payload": {"code": 0, "data": {"shop_id": "shop-a"}}},
        ],
        ("GET", "/governance/shop/experiencescore/getAnalysisScore"): [
            {"payload": {"code": 0, "data": {"shop_id": "shop-a"}}},
        ],
    }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            _ = (args, kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            _ = (exc_type, exc, tb)
            return None

        async def get(self, path, params=None, headers=None):
            _ = params
            cookie_log.append((str(path), str((headers or {}).get("Cookie") or "")))
            return _dispatch("GET", str(path))

        async def post(self, path, params=None, headers=None, json=None):
            _ = (params, headers, json)
            return _dispatch("POST", str(path))

    def _dispatch(method: str, path: str):
        queue = events.get((method, path))
        if not queue:
            raise RuntimeError(f"missing_event:{method}:{path}")
        current = queue.pop(0)
        if isinstance(current, Exception):
            raise current
        if isinstance(current, dict):
            return _FakeResponse(
                status_code=int(current.get("status_code", 200)),
                payload=current.get("payload"),
                cookies=current.get("cookies"),
            )
        if isinstance(current, _FakeResponse):
            return current
        raise RuntimeError(f"unsupported_event:{method}:{path}")

    monkeypatch.setattr(module.httpx, "AsyncClient", _FakeAsyncClient)

    store = SessionStateStore(base_dir=tmp_path)
    bootstrapper = SessionBootstrapper(state_store=store)
    runtime = _build_runtime()

    result = await bootstrapper.bootstrap_shop(
        runtime=runtime,
        shop_id="shop-a",
        verify_metric_date="2026-03-01",
    )

    assert result["bootstrap_failed"] is False
    overview_cookies = [
        cookie
        for path, cookie in cookie_log
        if path == "/governance/shop/experiencescore/getOverviewByVersion"
    ]
    assert len(overview_cookies) >= 2
    assert overview_cookies[0] == "sid=token"
    assert overview_cookies[1] == "sid=new-verify-token"
