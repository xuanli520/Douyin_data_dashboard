from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from functools import wraps
import json
import secrets
from datetime import datetime
from typing import Any
import redis
from loguru import logger


def get_redis_client() -> redis.Redis:
    if BaseTask._redis is None:
        BaseTask._redis = create_redis_connection()
    return BaseTask._redis


def acquire_lock(key: str, ttl: int = 300) -> str | None:
    token = secrets.token_hex(16)
    lock_key = f"douyin:lock:{key}"
    try:
        client = get_redis_client()
        if client.set(lock_key, token, nx=True, ex=ttl):
            return token
        return None
    except Exception as e:
        logger.warning(f"Failed to acquire lock: {e}", exc_info=True)
        return None


RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


def release_lock(key: str, token: str) -> bool:
    lock_key = f"douyin:lock:{key}"
    try:
        client = get_redis_client()
        result = client.eval(RELEASE_LOCK_SCRIPT, 1, lock_key, token)
        return result == 1
    except Exception as e:
        logger.warning(f"Failed to release lock: {e}", exc_info=True)
        return False


def cache_result(key: str, value: Any, ttl: int = 3600) -> bool:
    cache_key = f"douyin:cache:{key}"
    try:
        client = get_redis_client()
        serialized = json.dumps(value, default=str, ensure_ascii=False)
        client.setex(cache_key, ttl, serialized)
        return True
    except Exception as e:
        logger.warning(f"Failed to cache result: {e}", exc_info=True)
        return False


def get_cached_result(key: str) -> dict | None:
    cache_key = f"douyin:cache:{key}"
    try:
        client = get_redis_client()
        data = client.get(cache_key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        logger.warning(f"Failed to get cached result: {e}", exc_info=True)
        return None


def create_redis_connection():
    from src.config import get_settings

    settings = get_settings()
    return redis.Redis(
        host=settings.cache.host,
        port=settings.cache.port,
        db=settings.cache.db,
        password=settings.cache.password,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


class BaseTask(Task):
    _redis = None

    @property
    def sync_redis(self) -> redis.Redis:
        if BaseTask._redis is None:
            BaseTask._redis = create_redis_connection()
        return BaseTask._redis

    def get_state_key(self, task_id: str) -> str:
        return f"douyin:task:status:{task_id}"

    def _normalize_redis_hash(self, data: dict) -> dict:
        out = {}
        for k, v in data.items():
            if v is None:
                continue
            if isinstance(v, (dict, list)):
                try:
                    out[k] = json.dumps(v, ensure_ascii=False, default=str)[:2000]
                except Exception:
                    out[k] = str(v)[:2000]
            elif isinstance(v, bool):
                out[k] = "true" if v else "false"
            else:
                out[k] = str(v)[:2000]
        return out

    def _safe_update_status(self, task_id: str, status: str, data: dict):
        try:
            key = self.get_state_key(task_id)
            mapping = self._normalize_redis_hash({**data, "status": status})
            pipe = self.sync_redis.pipeline()
            pipe.hset(key, mapping=mapping)
            pipe.expire(key, 60)
            pipe.execute()
        except Exception as e:
            logger.warning(f"Failed to update task status: {e}", exc_info=True)

    def _safe_delete_status(self, task_id: str):
        try:
            self.sync_redis.delete(self.get_state_key(task_id))
        except Exception as e:
            logger.warning(f"Failed to delete task status: {e}", exc_info=True)

    def before_start(self, task_id: str, args: tuple, kwargs: dict):
        safe_args = str(args)[:200] if args else ""
        safe_kwargs = str(kwargs)[:200] if kwargs else ""

        triggered_by = kwargs.get("triggered_by") if kwargs else None

        self._safe_update_status(
            task_id,
            "STARTED",
            {
                "started_at": datetime.now().isoformat(),
                "task_name": self.name,
                "args": safe_args,
                "kwargs": safe_kwargs,
                "triggered_by": triggered_by,
            },
        )

        logger.bind(
            task_id=task_id,
            task_name=self.name,
            triggered_by=triggered_by,
            queue=self.request.delivery_info.get("routing_key")
            if self.request
            else None,
        ).info(f"Task {task_id} started")

    def after_return(
        self,
        status: str,
        retval: Any,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: Any,
    ):
        result_preview = None
        error_msg = None
        triggered_by = kwargs.get("triggered_by") if kwargs else None

        if status == "SUCCESS" and retval is not None:
            try:
                result_str = json.dumps(retval, default=str, ensure_ascii=False)
                result_preview = result_str[:2000]
            except Exception:
                result_preview = f"<unserializable: {type(retval)}>"
        elif status == "FAILURE":
            error_msg = str(einfo)[:2000] if einfo else "Unknown error"
        elif status == "RETRY":
            error_msg = str(einfo)[:500] if einfo else None

        self._safe_update_status(
            task_id,
            status,
            {
                "completed_at": datetime.now().isoformat(),
                "task_name": self.name,
                "triggered_by": triggered_by,
                "result": result_preview,
                "error": error_msg,
            },
        )

        logger.bind(
            task_id=task_id,
            task_name=self.name,
            triggered_by=triggered_by,
            status=status,
        ).info(f"Task {task_id} finished with status: {status}")

    def on_timeout(self, soft: bool, timeout: int):
        task_id = self.request.id
        if soft:
            logger.warning(f"Task {task_id} soft time limit ({timeout}s) exceeded")
        else:
            logger.error(f"Task {task_id} hard time limit ({timeout}s) exceeded")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        is_timeout = isinstance(exc, (SoftTimeLimitExceeded, TimeoutError))
        if not is_timeout:
            logger.error(f"Task {task_id} failed: {exc}", exc_info=True)
        else:
            logger.warning(f"Task {task_id} failed due to timeout: {exc}")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.warning(f"Task {task_id} retrying: {exc}")


def run_with_timeout_protection(task_func):
    @wraps(task_func)
    def wrapper(self, *args, **kwargs):
        try:
            return task_func(self, *args, **kwargs)
        except SoftTimeLimitExceeded:
            logger.warning(f"Task {self.request.id} soft time limit exceeded")
            raise

    return wrapper
