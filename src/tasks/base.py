from __future__ import annotations

from datetime import datetime
from typing import Any

from src.tasks.funboost_compat import AbstractConsumer, FunctionResultStatus, fct
from src.tasks.status_store import write_finished_task_status, write_started_task_status


def write_started_status_safe(
    task_func: Any,
    task_name: str,
    triggered_by: int | None,
    *,
    logger: Any,
    execution_id: int | None = None,
) -> datetime | None:
    try:
        raw_task_id = getattr(fct, "task_id", None)
        task_id = str(raw_task_id).strip() if raw_task_id is not None else ""
        if not task_id:
            logger.warning(
                "skip writing started task status because task_id is missing: %s",
                task_name,
            )
            return None
        return write_started_task_status(
            owner=task_func,
            task_id=task_id,
            task_name=task_name,
            triggered_by=triggered_by,
            execution_id=execution_id,
        )
    except Exception:
        logger.exception("failed to write started task status: %s", task_name)
        return None


class TaskStatusMixin(AbstractConsumer):
    @staticmethod
    def _should_skip_status_sync(*, queue_name: str) -> bool:
        return queue_name.endswith("_dlx")

    @staticmethod
    def _normalize_int(value: object, *, allow_float: bool = False) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if allow_float and isinstance(value, float):
            return int(value) if value.is_integer() else None
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return int(text)
            except ValueError:
                if not allow_float:
                    return None
                try:
                    float_value = float(text)
                except ValueError:
                    return None
                return int(float_value) if float_value.is_integer() else None
        return None

    @classmethod
    def _resolve_processed_rows(
        cls,
        *,
        body: object,
        result: object,
    ) -> int | None:
        if isinstance(result, dict):
            if "processed_rows" in result:
                normalized = cls._normalize_int(
                    result.get("processed_rows"),
                    allow_float=True,
                )
                if normalized is not None:
                    return max(normalized, 0)
        if isinstance(body, dict) and "processed_rows" in body:
            normalized = cls._normalize_int(
                body.get("processed_rows"),
                allow_float=True,
            )
            if normalized is not None:
                return max(normalized, 0)
        return None

    @classmethod
    def _resolve_triggered_by(
        cls,
        *,
        body: object,
        result: object,
    ) -> int | None:
        normalized = None
        if isinstance(result, dict):
            normalized = cls._normalize_int(result.get("triggered_by"))
        if normalized is None and isinstance(body, dict):
            normalized = cls._normalize_int(body.get("triggered_by"))
        if normalized is None or normalized <= 0:
            return None
        return normalized

    @staticmethod
    def _resolve_error_message(
        *,
        body: object,
        result: object,
        exception_msg: object,
        success: bool,
    ) -> str | None:
        if success:
            return None
        error_message = None
        if isinstance(result, dict):
            result_error = result.get("error_message")
            if isinstance(result_error, str) and result_error:
                error_message = result_error
        if error_message is None and isinstance(body, dict):
            body_error = body.get("error_message")
            if isinstance(body_error, str) and body_error:
                error_message = body_error
        if error_message is None and isinstance(exception_msg, str) and exception_msg:
            error_message = exception_msg
        return error_message

    def _sync_and_aio_frame_custom_record_process_info_func(
        self, current_function_result_status: FunctionResultStatus, kw: dict
    ) -> None:
        task_id = ""
        task_name = ""
        success = False
        body: object = None
        result: object = None
        triggered_by: int | None = None
        processed_rows: int | None = None
        try:
            raw_task_id = getattr(current_function_result_status, "task_id", None)
            task_id = str(raw_task_id or "").strip()
            task_name = str(
                getattr(current_function_result_status, "function", "") or ""
            )
            queue_name = str(getattr(self, "queue_name", "") or "").strip()
            if self._should_skip_status_sync(queue_name=queue_name):
                return
            if not task_id:
                self.logger.error(
                    "skip writing task status because task_id is missing function=%s",
                    task_name,
                )
                return
            body = kw.get("body", {}) if isinstance(kw, dict) else {}
            result = getattr(current_function_result_status, "result", None)
            success = bool(current_function_result_status.success)
            triggered_by = self._resolve_triggered_by(body=body, result=result)
            processed_rows = self._resolve_processed_rows(body=body, result=result)
            error_message = self._resolve_error_message(
                body=body,
                result=result,
                exception_msg=getattr(
                    current_function_result_status, "exception_msg", None
                ),
                success=success,
            )
            publisher = getattr(self, "publisher", None)
            status_owner = publisher if publisher is not None else self

            write_finished_task_status(
                owner=status_owner,
                task_id=task_id,
                task_name=task_name,
                success=success,
                completed_at=current_function_result_status.time_end,
                triggered_by=triggered_by,
                processed_rows=processed_rows,
                error_message=error_message,
            )
        except Exception:
            self.logger.exception(
                "failed to write task status: "
                "task_id=%s function=%s success=%s "
                "body_type=%s result_type=%s "
                "triggered_by=%s processed_rows=%s",
                task_id,
                task_name,
                success,
                type(body).__name__,
                type(result).__name__,
                triggered_by,
                processed_rows,
            )
