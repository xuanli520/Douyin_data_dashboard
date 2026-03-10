from src.tasks.funboost_compat import AbstractConsumer, FunctionResultStatus
from src.tasks.status_store import write_finished_task_status


class TaskStatusMixin(AbstractConsumer):
    def _sync_and_aio_frame_custom_record_process_info_func(
        self, current_function_result_status: FunctionResultStatus, kw: dict
    ) -> None:
        task_id = "unknown"
        try:
            task_id = str(current_function_result_status.task_id)
            body = kw.get("body", {})
            triggered_by = body.get("triggered_by") if isinstance(body, dict) else None
            processed_rows = (
                body.get("processed_rows", 0) if isinstance(body, dict) else 0
            )
            error_message = (
                body.get("error_message") if isinstance(body, dict) else None
            )
            write_finished_task_status(
                owner=self,
                task_id=task_id,
                task_name=current_function_result_status.function,
                success=bool(current_function_result_status.success),
                completed_at=current_function_result_status.time_end,
                triggered_by=triggered_by,
                processed_rows=processed_rows if isinstance(processed_rows, int) else 0,
                error_message=error_message if isinstance(error_message, str) else None,
            )
        except Exception:
            self.logger.exception("failed to write task status: %s", task_id)
