from src.config import get_settings
from src.tasks.funboost_compat import AbstractConsumer, FunctionResultStatus


class TaskStatusMixin(AbstractConsumer):
    def _sync_and_aio_frame_custom_record_process_info_func(
        self, current_function_result_status: FunctionResultStatus, kw: dict
    ) -> None:
        task_id = "unknown"
        try:
            redis_client = self.publisher.redis_db_frame
            task_id = str(current_function_result_status.task_id)
            body = kw.get("body", {})
            triggered_by = body.get("triggered_by") if isinstance(body, dict) else None
            key = f"douyin:task:status:{task_id}"
            redis_client.hset(
                key,
                mapping={
                    "status": (
                        "SUCCESS"
                        if current_function_result_status.success
                        else "FAILURE"
                    ),
                    "completed_at": current_function_result_status.time_end,
                    "task_name": current_function_result_status.function,
                    "triggered_by": triggered_by if triggered_by is not None else "",
                },
            )
            redis_client.expire(key, get_settings().funboost.status_ttl_seconds)
        except Exception:
            self.logger.exception("failed to write task status: %s", task_id)
