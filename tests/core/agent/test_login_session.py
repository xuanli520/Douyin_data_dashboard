import json
from pathlib import Path

import pytest

from src.core.agent.login import HumanInputBroker
from src.core.agent.login import HumanInputCancelled
from src.core.agent.login import HumanInputTimeout
from src.core.agent.login import LoginSession
from src.core.agent.login import build_login_tool_registry
from src.core.agent.tools import ToolCall
from src.core.agent.tools import ToolRegistry


def test_human_input_broker_memory_resolve_wait_and_cancel():
    broker = HumanInputBroker(allow_memory_fallback=True)
    broker.resolve("session-1", "123456")

    assert broker.wait("session-1", "请输入短信验证码", timeout_seconds=1) == "123456"

    broker.cancel("session-2")
    with pytest.raises(HumanInputCancelled):
        broker.wait("session-2", "请输入短信验证码", timeout_seconds=1)

    with pytest.raises(HumanInputTimeout):
        broker.wait("session-3", "请输入短信验证码", timeout_seconds=0)


def test_human_input_broker_redis_preserves_early_code():
    redis = _FakeRedis()
    broker = HumanInputBroker(redis_client=redis, ttl_seconds=60)

    broker.resolve("session-1", "654321")

    assert broker.wait("session-1", "请输入短信验证码", timeout_seconds=1) == "654321"
    assert ("agent_login:session-1:input", 60) in redis.expired
    assert redis.status["agent_login:session-1:status"] == "waiting"


def test_login_tool_registry_is_local_to_login_session():
    login_registry = build_login_tool_registry()

    assert "request_verification_code" in login_registry.names()
    assert "check_login_status" in login_registry.names()
    assert "request_verification_code" not in ToolRegistry().names()


def test_login_session_runs_deterministic_recipe_and_saves_state():
    driver = _FakeDriver()
    broker = HumanInputBroker(allow_memory_fallback=True)
    broker.resolve("login-1", "123456")
    state_store = _StateStore()
    manager = _LoginStateManager()
    events = []

    result = LoginSession(
        session_id="login-1",
        account_id="acct-1",
        phone="13800138000",
        driver=driver,
        broker=broker,
        state_store=state_store,
        login_state_manager=manager,
        event_sink=events.append,
    ).run()

    assert result.logged_in is True
    assert state_store.saved[0][0] == "acct-1"
    assert manager.active == ["acct-1"]
    assert ("fill", 'spinbutton "手机号码"', "13800138000") in driver.commands
    assert ("fill", 'spinbutton "验证码"', "123456") in driver.commands
    assert [event["event_type"] for event in events] == [
        "waiting_for_code",
        "login_success",
        "run_finished",
    ]
    assert "123456" not in json.dumps(events, ensure_ascii=False)


def test_login_session_tries_locator_fallback():
    driver = _FakeDriver(fail_once={'spinbutton "手机号码"'})
    broker = HumanInputBroker(allow_memory_fallback=True)
    broker.resolve("login-2", "123456")

    result = LoginSession(
        session_id="login-2",
        account_id="acct-1",
        phone="13800138000",
        driver=driver,
        broker=broker,
        state_store=_StateStore(),
        login_state_manager=_LoginStateManager(),
    ).run()

    assert result.logged_in is True
    assert ("fill", "input[placeholder*='手机号']", "13800138000") in driver.commands


def test_login_session_does_not_save_failed_login_state():
    driver = _FakeDriver(
        final_url="https://fxg.jinritemai.com/login/common",
        final_title="抖店登录-抖店后台-抖音电商后台",
        state={"cookies": [], "origins": []},
    )
    broker = HumanInputBroker(allow_memory_fallback=True)
    broker.resolve("login-3", "123456")
    state_store = _StateStore()

    result = LoginSession(
        session_id="login-3",
        account_id="acct-1",
        phone="13800138000",
        driver=driver,
        broker=broker,
        state_store=state_store,
        login_state_manager=_LoginStateManager(),
    ).run()

    assert result.logged_in is False
    assert state_store.saved == []


def test_login_session_fallback_intercepts_login_tools():
    driver = _FakeDriver(
        fail_always={"button.get-code-btn", "获取验证码", "发送验证码"}
    )
    broker = HumanInputBroker(allow_memory_fallback=True)
    broker.resolve("login-4", "123456")
    llm = _LLM(
        [
            ToolCall(name="request_verification_code", arguments={}),
            ToolCall(
                name="goto",
                arguments={
                    "url": "https://fxg.jinritemai.com/ffa/mshop/homepage/index"
                },
            ),
            ToolCall(name="check_login_status", arguments={}),
        ]
    )

    result = LoginSession(
        session_id="login-4",
        account_id="acct-1",
        phone="13800138000",
        driver=driver,
        broker=broker,
        state_store=_StateStore(),
        login_state_manager=_LoginStateManager(),
        llm_client=llm,
        max_steps=5,
    ).run()

    assert result.logged_in is True
    assert "request_verification_code" not in [item[0] for item in driver.commands]
    assert [request.step_index for request in llm.requests] == [0, 1, 2]


class _FakeDriver:
    def __init__(
        self,
        *,
        fail_once=None,
        fail_always=None,
        final_url="https://fxg.jinritemai.com/ffa/mshop/homepage/index",
        final_title="首页",
        state=None,
    ):
        self.commands = []
        self.fail_once = set(fail_once or set())
        self.fail_always = set(fail_always or set())
        self.final_url = final_url
        self.final_title = final_title
        self.state = state or {
            "cookies": [
                {
                    "name": "sessionid",
                    "value": "sid",
                    "domain": ".jinritemai.com",
                }
            ],
            "origins": [],
        }
        self.url = ""
        self.title_value = ""

    def open(self, url, *, headed=False):
        self.commands.append(("open", url, headed))
        self.url = url
        self.title_value = "抖店登录-抖店后台-抖音电商后台"

    def close(self):
        self.commands.append(("close",))

    def fill(self, locator, value):
        self._maybe_fail(locator.value)
        self.commands.append(("fill", locator.value, value))
        return {"ok": True}

    def click(self, locator):
        self._maybe_fail(locator.value)
        self.commands.append(("click", locator.value))
        if locator.value in {'button "登录"', "button.login-btn"}:
            self.url = self.final_url
            self.title_value = self.final_title
        return {"ok": True}

    def goto(self, url):
        self.commands.append(("goto", url))
        self.url = url
        self.title_value = "首页" if "/login" not in url else "抖店登录"
        return {"ok": True}

    def state_save(self, path: Path):
        Path(path).write_text(json.dumps(self.state), encoding="utf-8")

    def current_url(self):
        return self.url

    def title(self):
        return self.title_value

    def get_current_url(self):
        return self.current_url()

    def get_page_title(self):
        return self.title()

    def get_snapshot(self):
        return ""

    def capture_screenshot(self):
        return "screenshot.png"

    def _maybe_fail(self, locator_value):
        if locator_value in self.fail_always:
            raise RuntimeError("locator failed")
        if locator_value in self.fail_once:
            self.fail_once.remove(locator_value)
            raise RuntimeError("locator failed")


class _StateStore:
    def __init__(self):
        self.saved = []

    def save_playwright_state(self, account_id, state, shop_id=None):
        self.saved.append((account_id, state, shop_id))


class _LoginStateManager:
    def __init__(self):
        self.active = []

    async def mark_active(self, account_id):
        self.active.append(account_id)


class _LLM:
    def __init__(self, calls):
        self.calls = list(calls)
        self.requests = []

    def complete_tool_call(self, request):
        self.requests.append(request)
        return self.calls.pop(0)


class _FakeRedis:
    def __init__(self):
        self.lists = {}
        self.status = {}
        self.hashes = {}
        self.expired = []

    def set(self, key, value, ex=None):
        self.status[key] = value
        if ex is not None:
            self.expired.append((key, ex))

    def hset(self, key, mapping):
        self.hashes[key] = dict(mapping)

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def blpop(self, key, timeout=0):
        values = self.lists.get(key) or []
        if not values:
            return None
        return key, values.pop(0)

    def expire(self, key, ttl):
        self.expired.append((key, ttl))
