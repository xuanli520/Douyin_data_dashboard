import pytest

from src.scrapers.shop_dashboard.login_state import check_login_status


class _FakeRequest:
    async def get(self, _url: str, timeout: float):  # noqa: ARG002
        raise RuntimeError("not called")


class _FakePage:
    def __init__(self):
        self.url = "https://fxg.jinritemai.com/compass/overview"
        self.request = _FakeRequest()

    async def wait_for_selector(self, _selector: str, timeout: int):  # noqa: ARG002
        raise TimeoutError("not found")


@pytest.fixture
def fake_page():
    return _FakePage()


async def test_check_login_status_url_layer_returns_false(fake_page):
    fake_page.url = "https://fxg.jinritemai.com/login/common"
    assert await check_login_status(fake_page) is False
