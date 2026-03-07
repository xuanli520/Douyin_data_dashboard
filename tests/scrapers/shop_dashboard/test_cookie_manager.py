import fakeredis
from redis.exceptions import ResponseError

from src.scrapers.shop_dashboard.cookie_manager import CookieManager


def test_cookie_manager_no_longer_writes_cookie_to_redis():
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    manager = CookieManager(redis_client=fake_redis)

    manager.set("acct-1", {"x_tt_token": "abc"})

    assert fake_redis.hgetall("douyin:shop_dashboard:cookie:acct-1") == {}


class _EvalOnlyRedis:
    def __init__(self):
        self._store: dict[str, str] = {}
        self.eval_calls = 0

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        _ = ex
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True

    def get(self, key: str) -> str | None:
        raise AssertionError("atomic release must not call get")

    def delete(self, key: str) -> int:
        raise AssertionError("atomic release must not call delete")

    def eval(self, _script: str, _numkeys: int, key: str, token: str) -> int:
        self.eval_calls += 1
        if self._store.get(key) == token:
            del self._store[key]
            return 1
        return 0


def test_cookie_refresh_lock_release_is_atomic():
    fake_redis = _EvalOnlyRedis()
    manager = CookieManager(redis_client=fake_redis)
    lock_key = manager._lock_key("shop-1")
    fake_redis._store[lock_key] = "old-owner-token"

    manager._release_refresh_lock("shop-1", "old-owner-token")

    assert fake_redis.eval_calls == 1
    assert lock_key not in fake_redis._store


class _EvalUnsupportedRedis:
    def __init__(self):
        self._store: dict[str, str] = {}
        self.get_calls = 0
        self.delete_calls = 0

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        _ = ex
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True

    def eval(self, _script: str, _numkeys: int, *_args):
        raise ResponseError("unknown command 'eval'")

    def get(self, key: str) -> str | None:
        self.get_calls += 1
        return self._store.get(key)

    def delete(self, key: str) -> int:
        self.delete_calls += 1
        if key in self._store:
            del self._store[key]
            return 1
        return 0


def test_cookie_refresh_lock_release_falls_back_when_eval_not_supported():
    fake_redis = _EvalUnsupportedRedis()
    manager = CookieManager(redis_client=fake_redis)
    lock_key = manager._lock_key("shop-1")
    fake_redis._store[lock_key] = "token-a"

    manager._release_refresh_lock("shop-1", "token-a")

    assert lock_key not in fake_redis._store
    assert fake_redis.get_calls == 1
    assert fake_redis.delete_calls == 1
