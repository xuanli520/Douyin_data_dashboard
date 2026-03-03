from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable

from pydantic import BaseModel

_FORCE_LOCAL_COMPAT = os.getenv("TASKS_FUNBOOST_COMPAT_MODE", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

if not _FORCE_LOCAL_COMPAT:
    try:
        from funboost import (  # type: ignore
            ApsJobAdder,
            AbstractConsumer,
            BoosterParams,
            BrokerEnum,
            boost,
            fct,
        )
        from funboost.constant import ConcurrentModeEnum  # type: ignore
        from funboost.core.exceptions import FunboostException  # type: ignore
        from funboost.core.function_result_status_saver import (  # type: ignore
            FunctionResultStatus,
        )
    except ModuleNotFoundError:
        _FORCE_LOCAL_COMPAT = True

if _FORCE_LOCAL_COMPAT:

    class BrokerEnum:
        REDIS_ACK_ABLE = "REDIS_ACK_ABLE"
        REDIS_STREAM = "REDIS_STREAM"
        MEMORY_QUEUE = "MEMORY_QUEUE"

    class ConcurrentModeEnum:
        THREADING = "THREADING"
        SINGLE_THREAD = "SINGLE_THREAD"
        ASYNC = "ASYNC"

    class BoosterParams(BaseModel):
        queue_name: str
        broker_kind: str = BrokerEnum.REDIS_ACK_ABLE
        max_retry_times: int = 3
        retry_interval: int = 60
        function_timeout: int = 3600
        is_using_rpc_mode: bool = False
        broker_exclusive_config: dict[str, Any] = {}
        qps: float | int | None = None
        concurrent_num: int = 1
        concurrent_mode: str = ConcurrentModeEnum.THREADING
        consumer_override_cls: type | None = None
        consuming_function_decorator: Callable | None = None
        is_push_to_dlx_queue_when_retry_max_times: bool = False

        model_config = {"extra": "allow"}

    class _InMemoryRedis:
        def __init__(self):
            self._kv: dict[str, str] = {}
            self._hash: dict[str, dict[str, Any]] = {}

        def hset(self, key: str, mapping: dict[str, Any]) -> None:
            self._hash.setdefault(key, {}).update(mapping)

        def hgetall(self, key: str) -> dict[str, Any]:
            return dict(self._hash.get(key, {}))

        def expire(self, _key: str, _seconds: int) -> bool:
            return True

        def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
            if nx and key in self._kv:
                return False
            self._kv[key] = value
            return True

        def get(self, key: str) -> str | None:
            return self._kv.get(key)

        def eval(self, script: str, numkeys: int, *args):
            _ = script
            _ = numkeys
            key = args[0]
            token = args[1]
            if "del" in script:
                if self._kv.get(key) == token:
                    del self._kv[key]
                    return 1
                return 0
            if "expire" in script:
                return 1 if self._kv.get(key) == token else 0
            return 0

    class _Logger:
        def exception(self, *_args, **_kwargs):
            return None

        def error(self, *_args, **_kwargs):
            return None

        def info(self, *_args, **_kwargs):
            return None

    class AbstractConsumer:
        def __init__(self):
            self.publisher = SimpleNamespace(redis_db_frame=_InMemoryRedis())
            self.logger = _Logger()

    @dataclass
    class FunctionResultStatus:
        task_id: str
        success: bool
        time_end: float
        function: str

    class FunboostException(Exception):
        default_message = "Funboost exception"
        default_code = 0

        def __init__(self, message: str | None = None, error_data: dict | None = None):
            self.error_data = error_data or {}
            super().__init__(message or self.default_message)

    fct = SimpleNamespace(task_id="task-local", full_msg={})

    def boost(params: BoosterParams):
        def decorator(func: Callable):
            inner = func
            if params.consuming_function_decorator:
                inner = params.consuming_function_decorator(inner)

            def wrapper(*args, **kwargs):
                return inner(*args, **kwargs)

            redis_client = _InMemoryRedis()
            wrapper.__name__ = func.__name__
            wrapper.boost_params = params
            wrapper.publisher = SimpleNamespace(redis_db_frame=redis_client)
            wrapper.queue_name = params.queue_name
            wrapper.consume = lambda: None
            wrapper.multi_process_consume = lambda _n: None
            wrapper.push = lambda *a, **k: SimpleNamespace(
                task_id=f"task-{uuid.uuid4().hex}",
                queue_name=params.queue_name,
                args=a,
                kwargs=k,
            )
            return wrapper

        return decorator

    class ApsJobAdder:
        def __init__(self, _task_func: Callable, job_store_kind: str = "redis"):
            self.job_store_kind = job_store_kind
            self.jobs: list[dict[str, Any]] = []
            self.aps_obj = SimpleNamespace(
                get_jobs=lambda: list(self.jobs),
                pause_job=lambda _job_id: None,
                resume_job=lambda _job_id: None,
                remove_job=lambda _job_id: None,
            )

        def add_push_job(self, **kwargs) -> None:
            payload = dict(kwargs)
            payload.setdefault("created_at", time.time())
            self.jobs.append(payload)
