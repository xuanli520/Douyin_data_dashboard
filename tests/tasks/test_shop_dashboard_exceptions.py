from src.tasks.exceptions import (
    ShopDashboardCookieExpiredException,
    ShopDashboardDataIncompleteException,
    TaskErrorCode,
)


def test_shop_dashboard_cookie_expired_exception_defaults():
    exc = ShopDashboardCookieExpiredException()

    assert str(exc) == "Shop dashboard cookie expired"
    assert exc.default_code == TaskErrorCode.SHOP_DASHBOARD_COOKIE_EXPIRED


def test_shop_dashboard_data_incomplete_exception_defaults():
    exc = ShopDashboardDataIncompleteException()

    assert str(exc) == "Shop dashboard data incomplete"
    assert exc.default_code == TaskErrorCode.SHOP_DASHBOARD_DATA_INCOMPLETE
