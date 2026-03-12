from typing import Protocol


class RedisKey(Protocol):
    """Protocol for Redis key generators."""

    def __call__(self, **kwargs: str | int) -> str: ...


class _RefreshToken:
    """Refresh token key: refresh_token:{token_hash}"""

    namespace = "refresh_token"

    def __call__(self, token_hash: str) -> str:
        return f"{self.namespace}:{token_hash}"


class _UserRevoked:
    """User revoked key: user_revoked:{user_id}"""

    namespace = "user_revoked"

    def __call__(self, user_id: int) -> str:
        return f"{self.namespace}:{user_id}"


class _ShopDashboardShopCatalog:
    namespace = "shop_dashboard:shop_catalog"

    def __call__(self, account_id: str) -> str:
        return f"{self.namespace}:{account_id}"


class _ShopDashboardShopCatalogRefreshLock:
    namespace = "shop_dashboard:shop_catalog_refresh_lock"

    def __call__(self, account_id: str) -> str:
        return f"{self.namespace}:account:{account_id}"


class _ShopDashboardShopMismatchFailCount:
    namespace = "shop_dashboard:shop_mismatch_fail_count"

    def __call__(self, account_id: str, shop_id: str) -> str:
        return f"{self.namespace}:account:{account_id}:shop:{shop_id}"


class _ShopDashboardShopMismatchCircuit:
    namespace = "shop_dashboard:shop_mismatch_circuit"

    def __call__(self, account_id: str, shop_id: str) -> str:
        return f"{self.namespace}:account:{account_id}:shop:{shop_id}"


class RedisKeyRegistry:
    """Registry for all Redis keys used in the application."""

    refresh_token = _RefreshToken()
    user_revoked = _UserRevoked()
    shop_dashboard_shop_catalog = _ShopDashboardShopCatalog()
    shop_dashboard_shop_catalog_refresh_lock = _ShopDashboardShopCatalogRefreshLock()
    shop_dashboard_shop_mismatch_fail_count = _ShopDashboardShopMismatchFailCount()
    shop_dashboard_shop_mismatch_circuit = _ShopDashboardShopMismatchCircuit()


redis_keys = RedisKeyRegistry()
