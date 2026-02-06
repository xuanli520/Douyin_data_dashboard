import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.cache import CacheProtocol
from src.domains.data_import.enums import ImportStatus
from src.domains.data_import.models import DataImportRecord
from src.domains.data_import.parser import FileParser
from src.domains.data_import.mapping import FieldMapper
from src.domains.data_import.validator import ValidationService
from src.domains.data_import.repository import (
    DataImportRecordRepository,
    DataImportDetailRepository,
)


class ImportService:
    IMPORT_PREFIX = "import:"
    PROGRESS_KEY = "progress"
    CANCEL_KEY = "cancel"
    PARSE_CACHE_KEY = "parse_cache"
    DEFAULT_BATCH_SIZE = 1000

    def __init__(
        self,
        session: AsyncSession,
        redis: CacheProtocol | None = None,
    ):
        self.session = session
        self.redis = redis
        self.repo = DataImportRecordRepository(session)
        self.detail_repo = DataImportDetailRepository(session)

    def _get_progress_key(self, import_id: int) -> str:
        return f"{self.IMPORT_PREFIX}{import_id}:{self.PROGRESS_KEY}"

    def _get_cancel_key(self, import_id: int) -> str:
        return f"{self.IMPORT_PREFIX}{import_id}:{self.CANCEL_KEY}"

    def _get_parse_cache_key(self, import_id: int) -> str:
        return f"{self.IMPORT_PREFIX}{import_id}:{self.PARSE_CACHE_KEY}"

    async def _is_cancelled(self, import_id: int) -> bool:
        if not self.redis:
            return False
        try:
            return await self.redis.exists(self._get_cancel_key(import_id))
        except Exception:
            return False

    async def upload_file(
        self,
        file_path: str,
        file_name: str,
        file_size: int,
        file_type: str,
        data_source_id: int,
        batch_no: str,
        user_id: int | None = None,
    ) -> DataImportRecord:
        from src.domains.data_import.enums import FileType

        ft = FileType.EXCEL if file_type == "excel" else FileType.CSV

        record = await self.repo.create(
            {
                "file_name": file_name,
                "file_path": file_path,
                "file_size": file_size,
                "file_type": ft,
                "data_source_id": data_source_id,
                "batch_no": batch_no,
                "status": ImportStatus.PENDING,
                "created_by_id": user_id,
            }
        )
        await self.session.commit()
        return record

    async def parse_file(self, import_id: int) -> list[dict[str, Any]]:
        record = await self.repo.get_by_id(import_id)
        if not record:
            raise ValueError("Import record not found")

        if self.redis:
            try:
                cache_key = self._get_parse_cache_key(import_id)
                cached = await self.redis.get(cache_key)
                if cached:
                    cached_data = json.loads(cached)
                    if cached_data.get("file_path") == record.file_path:
                        return cached_data["rows"]
            except (json.JSONDecodeError, TypeError):
                pass

        try:
            parser = FileParser(record.file_path)
            rows = list(parser.parse())

            total_rows = len(rows)

            progress = {
                "stage": "parsing",
                "total": total_rows,
                "processed": total_rows,
            }
            if self.redis:
                await self.redis.set(
                    self._get_progress_key(import_id),
                    json.dumps(progress, ensure_ascii=False),
                    ttl=3600,
                )
                try:
                    cache_key = self._get_parse_cache_key(import_id)
                    await self.redis.set(
                        cache_key,
                        json.dumps(
                            {"file_path": record.file_path, "rows": rows},
                            ensure_ascii=False,
                        ),
                        ttl=3600,
                    )
                except Exception:
                    pass

            await self.repo.update_counts(import_id, total_rows=total_rows)
            await self.session.commit()

            return rows
        except Exception as e:
            await self.repo.update_status(import_id, ImportStatus.FAILED, str(e))
            await self.session.commit()
            raise

    async def apply_mapping(
        self,
        import_id: int,
        mappings: dict[str, str],
        target_fields: list[str],
    ) -> None:
        record = await self.repo.get_by_id(import_id)
        if not record:
            raise ValueError("Import record not found")

        mapper = FieldMapper()
        mapper.set_target_fields(target_fields)
        for source, target in mappings.items():
            mapper.add_manual_mapping(source, target)

        mapping_dict = mapper.get_mapping_dict()

        field_mapping = record.field_mapping or {}
        field_mapping.update(mapping_dict)

        await self.repo.update(import_id, {"field_mapping": field_mapping})
        await self.session.commit()

    async def validate_data(
        self, import_id: int, rows: list[dict[str, Any]], data_type: str = "order"
    ) -> dict[str, Any]:
        record = await self.repo.get_by_id(import_id)
        if not record:
            raise ValueError("Import record not found")

        await self.repo.update_status(import_id, ImportStatus.PROCESSING)
        await self.session.commit()

        field_mapping = record.field_mapping or {}

        mapper = FieldMapper()
        mapper.set_target_fields(list(field_mapping.values()))
        for source, target in field_mapping.items():
            mapper.add_manual_mapping(source, target)

        mapped_rows = [mapper.transform_data(row) for row in rows]

        results = ValidationService.validate_and_summarize(data_type, mapped_rows)

        if results["failed"] > 0:
            await self.repo.update_status(import_id, ImportStatus.VALIDATION_FAILED)
        else:
            await self.repo.update_status(import_id, ImportStatus.SUCCESS)
        await self.session.commit()

        return results

    async def confirm_import(
        self,
        import_id: int,
        rows: list[dict[str, Any]],
        batch_size: int | None = None,
    ) -> dict[str, Any]:
        record = await self.repo.get_by_id(import_id)
        if not record:
            raise ValueError("Import record not found")

        if record.status == ImportStatus.CANCELLED:
            raise ValueError("Import was cancelled")

        if record.status == ImportStatus.PROCESSING:
            raise ValueError("Import is processing")

        if record.status in [ImportStatus.SUCCESS, ImportStatus.PARTIAL]:
            if (record.success_rows or 0) > 0 or (record.failed_rows or 0) > 0:
                raise ValueError("Import has already been completed")

        if record.status == ImportStatus.FAILED:
            raise ValueError("Import has failed")

        batch_size = batch_size or self.DEFAULT_BATCH_SIZE

        if await self._is_cancelled(import_id):
            await self.repo.update_status(import_id, ImportStatus.CANCELLED)
            await self.session.commit()
            return {"cancelled": True}

        await self.repo.update_status(import_id, ImportStatus.PROCESSING)
        await self.session.commit()

        field_mapping = record.field_mapping or {}

        mapper = FieldMapper()
        mapper.set_target_fields(list(field_mapping.values()))
        for source, target in field_mapping.items():
            mapper.add_manual_mapping(source, target)

        processed = 0
        success = 0
        failed = 0
        errors: list[dict[str, Any]] = []
        batch_details: list[dict[str, Any]] = []

        for i, row in enumerate(rows):
            if await self._is_cancelled(import_id):
                await self.repo.update_status(import_id, ImportStatus.CANCELLED)
                await self.session.commit()
                return {"cancelled": True}

            row_number = i + 1
            processed += 1

            try:
                mapped_row = mapper.transform_data(row)

                detail = {
                    "import_record_id": import_id,
                    "row_number": row_number,
                    "row_data": mapped_row,
                    "status": ImportStatus.SUCCESS,
                    "error_message": None,
                }
                batch_details.append(detail)
                success += 1
            except Exception as e:
                detail = {
                    "import_record_id": import_id,
                    "row_number": row_number,
                    "row_data": row,
                    "status": ImportStatus.FAILED,
                    "error_message": str(e),
                }
                batch_details.append(detail)
                failed += 1
                errors.append(
                    {
                        "row": row_number,
                        "error": str(e),
                    }
                )

            if len(batch_details) >= batch_size:
                await self.detail_repo.bulk_create(batch_details)
                await self.repo.update_counts(
                    import_id,
                    success_rows=success,
                    failed_rows=failed,
                )
                await self.session.commit()
                batch_details = []

        if batch_details:
            await self.detail_repo.bulk_create(batch_details)

        await self.repo.update_counts(
            import_id,
            total_rows=processed,
            success_rows=success,
            failed_rows=failed,
        )
        await self.repo.mark_completed(import_id, success, failed)
        await self.session.commit()

        return {
            "total": processed,
            "success": success,
            "failed": failed,
            "errors": errors[:100],
        }

    async def get_import_record(self, import_id: int) -> DataImportRecord | None:
        return await self.repo.get_by_id(import_id)

    async def get_import_detail(self, import_id: int) -> DataImportRecord | None:
        return await self.repo.get_by_id(import_id, include_details=True)

    async def list_import_history(
        self,
        user_id: int | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        records, total = await self.repo.get_paginated(
            user_id=user_id,
            page=page,
            size=size,
        )
        return [
            {
                "id": r.id,
                "file_name": r.file_name,
                "data_source_id": r.data_source_id,
                "status": r.status,
                "total_rows": r.total_rows,
                "success_rows": r.success_rows,
                "failed_rows": r.failed_rows,
                "created_at": r.created_at,
            }
            for r in records
        ], total

    async def cancel_import(self, import_id: int) -> None:
        if self.redis:
            try:
                await self.redis.set(self._get_cancel_key(import_id), "1", ttl=3600)
            except Exception:
                pass
        await self.repo.update_status(import_id, ImportStatus.CANCELLED)
        await self.session.commit()

    async def get_progress(self, import_id: int) -> dict[str, Any] | None:
        if not self.redis:
            return None
        key = self._get_progress_key(import_id)
        try:
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            pass
        record = await self.repo.get_by_id(import_id)
        if record:
            return {
                "stage": record.status,
                "total": record.total_rows,
                "processed": record.success_rows + record.failed_rows,
                "success": record.success_rows,
                "failed": record.failed_rows,
            }
        return None
