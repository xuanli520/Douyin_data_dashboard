from __future__ import annotations

import inspect
import json
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from src import session as session_module
from src.core.agent.browser import DriverResult
from src.core.agent.llm import ToolSelectionRequest
from src.core.agent.models import LocatorSpec
from src.core.agent.models import SecurityPolicy
from src.core.agent.security import validate_locator
from src.core.agent.security import validate_navigation_target
from src.core.agent.security import validate_page_risk
from src.core.agent.security import validate_tool_name
from src.core.agent.tool_executor import ToolExecutor
from src.core.agent.tools import ToolArgument
from src.core.agent.tools import ToolCall
from src.core.agent.tools import ToolDefinition
from src.core.agent.tools import ToolRegistry

_CORE_EVENTS = frozenset(
    {
        "queued",
        "waiting_for_code",
        "code_submitted",
        "login_success",
        "login_failed",
        "login_cancelled",
        "run_finished",
    }
)
_DEBUG_EVENTS = frozenset(
    {"login_started", "page_observed", "tool_started", "tool_finished"}
)
_LOGIN_TOOLS = frozenset({"request_verification_code", "check_login_status"})
_LOGIN_URL_TOKENS = ("login/common", "/login", "passport", "/verify")
_LOGIN_TITLE_TOKENS = ("登录", "验证", "passport")
_VERIFICATION_CODE_SENT_PATTERN = re.compile(r"(?:\d{1,3}\s*[sS秒])|重新发送|已发送")
_DEFAULT_RECIPE_PATH = Path(__file__).with_name("login_recipe.yml")


class HumanInputTimeout(TimeoutError):
    pass


class HumanInputCancelled(RuntimeError):
    pass


class HumanInputBrokerUnavailable(RuntimeError):
    pass


@dataclass(slots=True)
class LoginResult:
    logged_in: bool
    status: str = "failed"
    reason: str = ""
    current_url: str = ""
    page_title: str = ""
    state: dict[str, Any] | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "logged_in": self.logged_in,
            "status": self.status,
            "reason": self.reason,
            "current_url": self.current_url,
            "page_title": self.page_title,
        }


class HumanInputBroker:
    _condition = threading.Condition()
    _memory_inputs: dict[str, list[dict[str, str]]] = {}
    _memory_status: dict[str, str] = {}
    _memory_meta: dict[str, dict[str, str]] = {}

    def __init__(
        self,
        *,
        redis_client: Any | None = None,
        prefix: str = "agent_login",
        ttl_seconds: int = 900,
        allow_memory_fallback: bool | None = None,
    ) -> None:
        self._redis = redis_client
        self._prefix = str(prefix or "agent_login").strip(":") or "agent_login"
        self._ttl_seconds = max(int(ttl_seconds), 1)
        if allow_memory_fallback is None:
            allow_memory_fallback = "PYTEST_CURRENT_TEST" in os.environ
        self._allow_memory_fallback = bool(allow_memory_fallback)

    def wait(
        self,
        session_id: str,
        prompt: str,
        *,
        timeout_seconds: int,
    ) -> str:
        timeout_seconds = int(timeout_seconds)
        if self._redis is None:
            if not self._allow_memory_fallback:
                raise HumanInputBrokerUnavailable("redis broker is unavailable")
            return self._memory_wait(session_id, prompt, timeout_seconds)
        return self._redis_wait(session_id, prompt, timeout_seconds)

    def resolve(self, session_id: str, code: str) -> None:
        payload = {"type": "code", "code": str(code)}
        if self._redis is None:
            if not self._allow_memory_fallback:
                raise HumanInputBrokerUnavailable("redis broker is unavailable")
            self._memory_push(session_id, payload)
            return
        self._redis_push(session_id, payload)

    def cancel(self, session_id: str) -> None:
        payload = {"type": "cancel"}
        if self._redis is None:
            if not self._allow_memory_fallback:
                raise HumanInputBrokerUnavailable("redis broker is unavailable")
            self._memory_push(session_id, payload)
            return
        self._redis_push(session_id, payload)

    def _redis_wait(self, session_id: str, prompt: str, timeout_seconds: int) -> str:
        if timeout_seconds <= 0:
            raise HumanInputTimeout("verification_code_timeout")
        deadline = time.monotonic() + timeout_seconds
        try:
            self._redis.set(
                self._status_key(session_id), "waiting", ex=self._ttl_seconds
            )
            self._redis.hset(
                self._meta_key(session_id),
                mapping={"prompt": prompt, "updated_at": str(int(time.time()))},
            )
            self._expire(session_id)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise HumanInputTimeout("verification_code_timeout")
                raw = self._redis.blpop(
                    self._input_key(session_id),
                    timeout=1,
                )
                if raw is not None:
                    break
        except Exception as exc:
            if isinstance(exc, HumanInputTimeout):
                raise
            raise HumanInputBrokerUnavailable("redis broker is unavailable") from exc
        message = _decode_broker_message(raw[1] if isinstance(raw, tuple) else raw)
        return _code_from_message(message)

    def _redis_push(self, session_id: str, payload: dict[str, str]) -> None:
        try:
            self._redis.rpush(
                self._input_key(session_id),
                json.dumps(payload, ensure_ascii=False),
            )
            self._expire(session_id)
        except Exception as exc:
            raise HumanInputBrokerUnavailable("redis broker is unavailable") from exc

    def _expire(self, session_id: str) -> None:
        for key in (
            self._input_key(session_id),
            self._status_key(session_id),
            self._meta_key(session_id),
        ):
            self._redis.expire(key, self._ttl_seconds)

    def _memory_wait(
        self,
        session_id: str,
        prompt: str,
        timeout_seconds: int,
    ) -> str:
        if timeout_seconds <= 0:
            raise HumanInputTimeout("verification_code_timeout")
        deadline = time.monotonic() + timeout_seconds
        input_key = self._input_key(session_id)
        with self._condition:
            self._memory_status[self._status_key(session_id)] = "waiting"
            self._memory_meta[self._meta_key(session_id)] = {
                "prompt": prompt,
                "updated_at": str(int(time.time())),
            }
            while True:
                queue = self._memory_inputs.setdefault(input_key, [])
                if queue:
                    return _code_from_message(queue.pop(0))
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise HumanInputTimeout("verification_code_timeout")
                self._condition.wait(remaining)

    def _memory_push(self, session_id: str, payload: dict[str, str]) -> None:
        with self._condition:
            self._memory_inputs.setdefault(self._input_key(session_id), []).append(
                payload
            )
            self._condition.notify_all()

    def _input_key(self, session_id: str) -> str:
        return f"{self._prefix}:{session_id}:input"

    def _status_key(self, session_id: str) -> str:
        return f"{self._prefix}:{session_id}:status"

    def _meta_key(self, session_id: str) -> str:
        return f"{self._prefix}:{session_id}:meta"


class LoginSession:
    def __init__(
        self,
        *,
        session_id: str,
        account_id: str,
        phone: str,
        driver: Any,
        broker: HumanInputBroker,
        state_store: Any,
        login_state_manager: Any,
        llm_client: Any | None = None,
        event_sink: Any | None = None,
        recipe_path: str | Path | None = None,
        allowed_origins: list[str] | None = None,
        headed: bool = False,
        code_timeout_seconds: int = 300,
        max_steps: int = 20,
        debug_events: bool = False,
    ) -> None:
        self._session_id = str(session_id)
        self._account_id = str(account_id)
        self._phone = str(phone)
        self._driver = driver
        self._broker = broker
        self._state_store = state_store
        self._login_state_manager = login_state_manager
        self._llm_client = llm_client
        self._event_sink = event_sink
        self._recipe_path = Path(recipe_path) if recipe_path else _DEFAULT_RECIPE_PATH
        self._allowed_origins = list(allowed_origins or [])
        self._headed = bool(headed)
        self._code_timeout_seconds = max(int(code_timeout_seconds), 1)
        self._max_steps = max(int(max_steps), 1)
        self._debug_events = bool(debug_events)
        self._verification_code: str | None = None
        self._registry = build_login_tool_registry()
        self._security_policy = SecurityPolicy(allowed_origins=self._allowed_origins)
        self._tool_executor = ToolExecutor(
            driver,
            registry=self._registry,
            security=_LoginSecurity(),
        )

    def run(self) -> LoginResult:
        recipe = self._load_recipe()
        entrypoint = str(recipe.get("entrypoint") or "").strip()
        if not self._allowed_origins:
            self._allowed_origins = [_origin(entrypoint)]
            self._security_policy = SecurityPolicy(
                allowed_origins=self._allowed_origins
            )
        self._emit(
            "login_started",
            status="running",
            message="login started",
            current_url=entrypoint,
        )
        result = LoginResult(False, reason="login_not_started")
        try:
            self._driver.open(entrypoint, headed=self._headed)
            result = self._run_deterministic_recipe(recipe)
            if result.logged_in:
                result = self._persist_success(result)
            self._emit_result(result)
            return result
        except HumanInputCancelled:
            result = LoginResult(
                False,
                status="cancelled",
                reason="cancelled",
                current_url=self._current_url(),
                page_title=self._page_title(),
            )
            self._emit_result(result)
            return result
        except HumanInputTimeout:
            result = LoginResult(
                False,
                reason="verification_code_timeout",
                current_url=self._current_url(),
                page_title=self._page_title(),
            )
            self._emit_result(result)
            return result
        except Exception as exc:
            result = LoginResult(
                False,
                reason=str(exc) or type(exc).__name__,
                current_url=self._current_url(),
                page_title=self._page_title(),
            )
            self._emit_result(result)
            return result
        finally:
            try:
                self._driver.close()
            finally:
                self._emit(
                    "run_finished",
                    status=result.status,
                    message=result.reason,
                    current_url=result.current_url,
                    page_title=result.page_title,
                )

    def _run_deterministic_recipe(self, recipe: dict[str, Any]) -> LoginResult:
        steps = recipe.get("steps")
        if not isinstance(steps, list):
            return LoginResult(False, reason="recipe_step_failed: steps missing")
        for step in steps:
            if not isinstance(step, dict):
                return LoginResult(False, reason="recipe_step_failed: invalid step")
            action = str(step.get("action") or "").strip()
            try:
                result = self._run_recipe_step(action, step)
            except (HumanInputCancelled, HumanInputTimeout):
                raise
            except Exception as exc:
                if bool(step.get("optional")):
                    continue
                return LoginResult(
                    False,
                    reason=f"recipe_step_failed: {step.get('id') or action}: {exc}",
                    current_url=self._current_url(),
                    page_title=self._page_title(),
                )
            if isinstance(result, LoginResult):
                return result
        return self._check_login_status()

    def _run_recipe_step(
        self,
        action: str,
        step: dict[str, Any],
    ) -> LoginResult | None:
        if action == "request_verification_code":
            self._verification_code = self._request_verification_code()
            return None
        if action == "check_login_status":
            return self._check_login_status()
        if action == "fill":
            value = self._value_from_step(step)
            self._try_locators(step, action="fill", value=value)
            self._assert_input_value(step, value)
            return None
        if action == "click":
            self._try_locators(step, action="click")
            if step.get("id") == "send_code":
                self._assert_verification_code_sent()
            return None
        if action == "click_js":
            self._try_locators(step, action="click_js")
            return None
        if action == "check":
            self._try_locators(step, action="check")
            return None
        raise ValueError(f"unsupported login recipe action: {action}")

    def _try_locators(
        self,
        step: dict[str, Any],
        *,
        action: str,
        value: str | None = None,
    ) -> DriverResult:
        locators = _step_locators(step)
        if not locators:
            raise ValueError("step has no locators")
        retry_count = 3 if action == "click" and step.get("id") == "send_code" else 1
        last_error: Exception | None = None
        for attempt in range(retry_count):
            for locator in locators:
                try:
                    self._emit_tool_started(action, step, locator, value)
                    if action == "fill":
                        result = self._driver.fill(locator, str(value or ""))
                    elif action == "check":
                        result = self._driver.check(locator)
                    elif action == "click_js":
                        click_js = getattr(self._driver, "click_js", None)
                        if callable(click_js):
                            result = click_js(locator)
                        else:
                            result = self._driver.click(locator)
                    else:
                        result = self._driver.click(locator)
                    self._emit_tool_finished(action, step, locator, result)
                    return result
                except Exception as exc:
                    last_error = exc
                    self._emit_tool_finished(action, step, locator, exc)
            if attempt + 1 < retry_count:
                time.sleep(1)
        raise last_error or RuntimeError("locator failed")

    def _assert_input_value(self, step: dict[str, Any], expected: str) -> None:
        if step.get("id") not in {"fill_phone", "fill_code"}:
            return
        reader = getattr(self._driver, "input_value", None)
        if not callable(reader):
            return
        last_error: Exception | None = None
        for locator in _step_locators(step):
            try:
                actual = str(reader(locator) or "").strip()
            except Exception as exc:
                last_error = exc
                continue
            if actual == str(expected).strip():
                return
        message = f"{step.get('id')}_value_not_applied"
        if last_error is not None:
            message = f"{message}: {last_error}"
        raise RuntimeError(message)

    def _assert_verification_code_sent(self) -> None:
        deadline = time.monotonic() + 10
        while True:
            page_text = self._page_text()
            if _verification_code_sent(page_text):
                return
            if time.monotonic() >= deadline:
                raise RuntimeError("verification_code_send_not_confirmed")
            time.sleep(0.5)

    def _request_verification_code(self) -> str:
        self._emit(
            "waiting_for_code",
            status="waiting",
            message="waiting for verification code",
            current_url=self._current_url(),
            page_title=self._page_title(),
        )
        return self._broker.wait(
            self._session_id,
            "请输入短信验证码",
            timeout_seconds=self._code_timeout_seconds,
        )

    def _run_react_fallback(self, entrypoint: str) -> LoginResult:
        observation = self._capture_observation([])
        history: list[dict[str, Any]] = []
        for step_index in range(self._max_steps):
            request = ToolSelectionRequest(
                goal="Complete managed web login with SMS verification code.",
                entrypoint_url=entrypoint,
                current_observation=observation,
                tool_history=history,
                available_tools=self._registry.prompt_payload(),
                step_index=step_index,
                max_steps=self._max_steps,
            )
            try:
                tool_call = self._registry.validate_tool_call(
                    self._llm_client.complete_tool_call(request)
                )
                result = self._execute_fallback_tool(tool_call)
                if isinstance(result, LoginResult):
                    if result.logged_in:
                        return result
                    history.append(_tool_history(step_index, tool_call, result.reason))
                    continue
                observation = self._capture_observation(
                    [{"tool_name": tool_call.name, "result": result}]
                )
                history.append(_tool_history(step_index, tool_call, result))
            except (HumanInputCancelled, HumanInputTimeout):
                raise
            except Exception as exc:
                history.append(_tool_history(step_index, None, str(exc), failed=True))
        return LoginResult(
            False,
            reason="max_steps_exceeded",
            current_url=self._current_url(),
            page_title=self._page_title(),
        )

    def _execute_fallback_tool(self, tool_call: ToolCall) -> Any:
        if tool_call.name == "request_verification_code":
            self._verification_code = self._request_verification_code()
            return {"status": "received"}
        if tool_call.name == "check_login_status":
            return self._check_login_status()
        if tool_call.name == "done":
            return self._check_login_status()
        self._emit(
            "tool_started",
            status="running",
            message=tool_call.name,
            current_url=self._current_url(),
            page_title=self._page_title(),
            metadata={"arguments": _sanitize_value(tool_call.arguments)},
        )
        result = self._tool_executor.execute(
            tool_call,
            security_policy=self._security_policy,
        )
        self._emit(
            "tool_finished",
            status="running",
            message=tool_call.name,
            current_url=self._current_url(),
            page_title=self._page_title(),
            metadata={"result": _json_safe(result)},
        )
        return result

    def _check_login_status(self) -> LoginResult:
        current_url = self._current_url()
        page_title = self._page_title()
        try:
            state = self._capture_storage_state()
        except Exception as exc:
            return LoginResult(
                False,
                reason=f"state_save_failed: {exc}",
                current_url=current_url,
                page_title=page_title,
            )
        url_ok = _url_ok(current_url, self._allowed_origins)
        title_ok = _title_ok(page_title)
        cookie_ok = _has_session_cookie(state)
        page_text = self._page_text()
        page_ok = _logged_in_page_text(page_text)
        login_form_visible = _login_form_visible(page_text)
        logged_in = (
            page_ok
            or (cookie_ok and not login_form_visible)
            or (cookie_ok and (url_ok or title_ok))
        )
        reason = (
            f"url_ok={url_ok}, title_ok={title_ok}, cookie_ok={cookie_ok}, "
            f"page_ok={page_ok}, login_form_visible={login_form_visible}"
        )
        return LoginResult(
            logged_in,
            status="succeeded" if logged_in else "failed",
            reason="" if logged_in else reason,
            current_url=current_url,
            page_title=page_title,
            state=state if logged_in else None,
        )

    def _capture_storage_state(self) -> dict[str, Any]:
        fd, temp_file = tempfile.mkstemp(
            prefix=f"agent-login-{self._session_id}-",
            suffix=".json",
        )
        os.close(fd)
        temp_path = Path(temp_file)
        try:
            self._driver.state_save(temp_path)
            payload = json.loads(temp_path.read_text(encoding="utf-8"))
        finally:
            if temp_path.exists():
                temp_path.unlink()
        return payload if isinstance(payload, dict) else {}

    def _persist_success(self, result: LoginResult) -> LoginResult:
        if result.state is None:
            return LoginResult(
                False,
                reason="state_missing",
                current_url=result.current_url,
                page_title=result.page_title,
            )
        try:
            self._state_store.save_playwright_state(self._account_id, result.state)
            marker = getattr(self._login_state_manager, "mark_active", None)
            if callable(marker):
                marked = marker(self._account_id)
                if inspect.isawaitable(marked):
                    session_module.run_coro(marked)
        except Exception as exc:
            return LoginResult(
                False,
                reason=f"state_persist_failed: {exc}",
                current_url=result.current_url,
                page_title=result.page_title,
            )
        return result

    def _emit_result(self, result: LoginResult) -> None:
        if result.logged_in:
            self._emit(
                "login_success",
                status="succeeded",
                message="login succeeded",
                current_url=result.current_url,
                page_title=result.page_title,
            )
            return
        event_type = (
            "login_cancelled" if result.status == "cancelled" else "login_failed"
        )
        self._emit(
            event_type,
            status=result.status,
            message=result.reason,
            current_url=result.current_url,
            page_title=result.page_title,
        )

    def _capture_observation(
        self, tool_results: list[dict[str, Any]]
    ) -> dict[str, Any]:
        try:
            observation = self._tool_executor.capture_observation(
                tool_results=tool_results,
                security_policy=self._security_policy,
            )
        except Exception:
            observation = {
                "current_url": self._current_url(),
                "page_title": self._page_title(),
                "screenshot_artifact_id": None,
                "snapshot_text": "",
                "tool_results": tool_results,
            }
        self._emit(
            "page_observed",
            status="running",
            message="page observed",
            current_url=str(observation.get("current_url") or ""),
            page_title=str(observation.get("page_title") or ""),
            screenshot_artifact_id=observation.get("screenshot_artifact_id"),
        )
        return observation

    def _emit_tool_started(
        self,
        action: str,
        step: dict[str, Any],
        locator: LocatorSpec,
        value: str | None,
    ) -> None:
        self._emit(
            "tool_started",
            status="running",
            message=action,
            current_url=self._current_url(),
            page_title=self._page_title(),
            metadata={
                "step_id": step.get("id"),
                "locator": locator.model_dump(mode="json"),
                "value": "[redacted]" if value is not None else None,
            },
        )

    def _emit_tool_finished(
        self,
        action: str,
        step: dict[str, Any],
        locator: LocatorSpec,
        result: Any,
    ) -> None:
        self._emit(
            "tool_finished",
            status="running",
            message=action,
            current_url=self._current_url(),
            page_title=self._page_title(),
            metadata={
                "step_id": step.get("id"),
                "locator": locator.model_dump(mode="json"),
                "result": _json_safe(result),
            },
        )

    def _emit(self, event_type: str, **payload: Any) -> None:
        if self._event_sink is None:
            return
        if event_type not in _CORE_EVENTS and not (
            (self._headed or self._debug_events) and event_type in _DEBUG_EVENTS
        ):
            return
        event = {
            "event_type": event_type,
            "current_url": str(payload.get("current_url") or ""),
            "page_title": str(payload.get("page_title") or ""),
            "screenshot_artifact_id": payload.get("screenshot_artifact_id"),
            "status": str(payload.get("status") or ""),
            "message": str(payload.get("message") or ""),
        }
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            event["metadata"] = _sanitize_value(metadata)
        self._event_sink(event)

    def _current_url(self) -> str:
        current_url = getattr(self._driver, "current_url", None)
        if callable(current_url):
            return str(current_url() or "")
        fallback = getattr(self._driver, "get_current_url", None)
        return str(fallback() if callable(fallback) else "")

    def _page_title(self) -> str:
        title = getattr(self._driver, "title", None)
        if callable(title):
            return str(title() or "")
        fallback = getattr(self._driver, "get_page_title", None)
        return str(fallback() if callable(fallback) else "")

    def _page_text(self) -> str:
        for name in ("page_text", "get_page_text", "get_snapshot", "snapshot"):
            reader = getattr(self._driver, name, None)
            if not callable(reader):
                continue
            try:
                return str(reader() or "")
            except Exception:
                continue
        return ""

    def _load_recipe(self) -> dict[str, Any]:
        payload = yaml.safe_load(self._recipe_path.read_text(encoding="utf-8"))
        recipe = payload.get("login_recipe") if isinstance(payload, dict) else None
        if not isinstance(recipe, dict):
            raise ValueError("login recipe is invalid")
        return recipe

    def _value_from_step(self, step: dict[str, Any]) -> str:
        source = str(step.get("value_from") or "").strip()
        if source == "phone":
            return self._phone
        if source == "code":
            if self._verification_code is None:
                raise ValueError("verification code is missing")
            return self._verification_code
        return str(step.get("value") or "")


class _LoginSecurity:
    DEFAULT_POLICY: dict[str, Any] = {}

    def validate_tool_name(self, tool_name: str) -> str:
        normalized = str(tool_name or "").strip()
        if normalized in _LOGIN_TOOLS:
            return normalized
        return validate_tool_name(normalized)

    def validate_locator(self, locator: Any) -> None:
        parsed = (
            locator
            if isinstance(locator, LocatorSpec)
            else LocatorSpec.model_validate(locator)
        )
        validate_locator(parsed)

    def validate_navigation_target(self, url: str, security_policy: Any | None) -> None:
        if security_policy is None:
            return
        validate_navigation_target(url, security_policy)

    def validate_page_risk(self, url: str, title: str, snapshot_text: str) -> None:
        validate_page_risk(url, title, snapshot_text)


def build_login_tool_registry() -> ToolRegistry:
    base_definitions = ToolRegistry().definitions()
    login_definitions = [
        ToolDefinition(
            name="request_verification_code",
            arguments=[ToolArgument(name="prompt")],
        ),
        ToolDefinition(name="check_login_status"),
    ]
    return ToolRegistry([*base_definitions, *login_definitions])


def _step_locators(step: dict[str, Any]) -> list[LocatorSpec]:
    locators = step.get("locators")
    if not isinstance(locators, list):
        return []
    return [_locator_from_value(item) for item in locators]


def _locator_from_value(value: Any) -> LocatorSpec:
    if isinstance(value, LocatorSpec):
        return value
    if not isinstance(value, dict):
        raise ValueError("invalid locator")
    if "kind" in value and "value" in value:
        return LocatorSpec.model_validate(value)
    if "css" in value:
        return LocatorSpec(kind="css", value=str(value["css"]))
    if "xpath" in value:
        return LocatorSpec(kind="xpath", value=str(value["xpath"]))
    if "text" in value:
        return LocatorSpec(kind="text", value=str(value["text"]))
    if "role" in value:
        role = str(value["role"]).strip()
        name = str(value.get("name") or "").strip()
        locator_value = f'{role} "{name}"' if name else role
        return LocatorSpec(kind="role", value=locator_value)
    raise ValueError("invalid locator")


def _decode_broker_message(value: Any) -> dict[str, str]:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            payload = {"type": "code", "code": value}
    elif isinstance(value, dict):
        payload = value
    else:
        payload = {}
    return {str(k): str(v) for k, v in payload.items()}


def _code_from_message(message: dict[str, str]) -> str:
    if message.get("type") == "cancel":
        raise HumanInputCancelled("cancelled")
    code = str(message.get("code") or "").strip()
    if not code:
        raise HumanInputTimeout("verification_code_missing")
    return code


def _url_ok(url: str, allowed_origins: list[str]) -> bool:
    normalized = str(url or "").strip()
    lowered = normalized.casefold()
    if not normalized or any(token in lowered for token in _LOGIN_URL_TOKENS):
        return False
    origin = _origin(normalized)
    allowed = {str(item).rstrip("/") for item in allowed_origins if str(item).strip()}
    return bool(origin and origin.rstrip("/") in allowed)


def _origin(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    return (
        f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    )


def _title_ok(title: str) -> bool:
    normalized = str(title or "").strip()
    if normalized == "首页":
        return True
    lowered = normalized.casefold()
    return bool(
        normalized and not any(token in lowered for token in _LOGIN_TITLE_TOKENS)
    )


def _has_session_cookie(state: dict[str, Any]) -> bool:
    cookies = state.get("cookies")
    if not isinstance(cookies, list):
        return False
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        domain = str(cookie.get("domain") or "")
        name = str(cookie.get("name") or "")
        if ".jinritemai.com" in domain and name == "sessionid":
            return True
    return False


def _verification_code_sent(page_text: str) -> bool:
    return bool(_VERIFICATION_CODE_SENT_PATTERN.search(str(page_text or "")))


def _logged_in_page_text(page_text: str) -> bool:
    normalized = str(page_text or "")
    return "请选择店铺" in normalized


def _login_form_visible(page_text: str) -> bool:
    normalized = str(page_text or "")
    return "手机登录" in normalized and "验证码" in normalized


def _tool_history(
    step_index: int,
    tool_call: ToolCall | None,
    result: Any,
    *,
    failed: bool = False,
) -> dict[str, Any]:
    return {
        "step_index": step_index,
        "tool_name": tool_call.name if tool_call is not None else "",
        "arguments": _sanitize_value(tool_call.arguments if tool_call else {}),
        "result": _json_safe(result),
        "status": "failed" if failed else "ok",
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, Exception):
        return {"error": str(value)}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in {"code", "value", "verification_code", "phone"}:
                redacted[key_text] = "[redacted]"
            else:
                redacted[key_text] = _sanitize_value(item)
        return redacted
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return _json_safe(value)
