import fakeredis
from redis.exceptions import ResponseError

from src.scrapers.shop_dashboard.lock_manager import LockManager


def test_lock_manager_keys():
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    lock = LockManager(redis_client=fake_redis)
    assert lock.account_lock_key("acct-1") == "douyin:account:lock:acct-1"
    assert lock.shop_lock_key("shop-1") == "douyin:shop:lock:shop-1"


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


def test_release_account_lock_is_atomic_and_does_not_delete_new_owner_lock():
    fake_redis = _EvalOnlyRedis()
    lock = LockManager(redis_client=fake_redis)
    key = lock.account_lock_key("acct-1")
    fake_redis._store[key] = "token-a"

    lock.release_account_lock("acct-1", "token-a")

    assert fake_redis.eval_calls == 1
    assert key not in fake_redis._store


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


def test_release_account_lock_falls_back_when_eval_not_supported():
    fake_redis = _EvalUnsupportedRedis()
    lock = LockManager(redis_client=fake_redis)
    key = lock.account_lock_key("acct-1")
    fake_redis._store[key] = "token-a"

    lock.release_account_lock("acct-1", "token-a")

    assert key not in fake_redis._store
    assert fake_redis.get_calls == 1
    assert fake_redis.delete_calls == 1
