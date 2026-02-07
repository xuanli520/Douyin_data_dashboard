import pytest
from datetime import datetime

from src.domains.data_import.enums import FileType, ImportStatus
from src.domains.data_import.models import DataImportDetail, DataImportRecord
from src.domains.data_import.repository import (
    DataImportDetailRepository,
    DataImportRecordRepository,
)


class TestImportStatusEnum:
    def test_enum_values(self):
        assert ImportStatus.PENDING.value == "PENDING"
        assert ImportStatus.PROCESSING.value == "PROCESSING"
        assert ImportStatus.SUCCESS.value == "SUCCESS"
        assert ImportStatus.FAILED.value == "FAILED"
        assert ImportStatus.PARTIAL.value == "PARTIAL"

    def test_enum_is_string(self):
        status = ImportStatus.SUCCESS
        assert isinstance(status, str)
        assert status == "SUCCESS"


class TestFileTypeEnum:
    def test_enum_values(self):
        assert FileType.EXCEL.value == "EXCEL"
        assert FileType.CSV.value == "CSV"

    def test_enum_is_string(self):
        file_type = FileType.CSV
        assert isinstance(file_type, str)
        assert file_type == "CSV"


class TestDataImportRecordModel:
    def test_default_values(self):
        record = DataImportRecord(
            batch_no="test-batch-001",
            file_name="test.xlsx",
            file_type=FileType.EXCEL,
            file_size=1024,
            file_path="/uploads/test.xlsx",
        )
        assert record.status == ImportStatus.PENDING
        assert record.total_rows == 0
        assert record.success_rows == 0
        assert record.failed_rows == 0
        assert record.field_mapping is None
        assert record.error_message is None
        assert record.started_at is None
        assert record.completed_at is None
        assert record.data_source_id is None

    def test_model_fields(self):
        record = DataImportRecord(
            id=1,
            batch_no="batch-123",
            data_source_id=10,
            file_name="data.csv",
            file_type=FileType.CSV,
            file_size=2048,
            file_path="/files/data.csv",
            status=ImportStatus.PROCESSING,
            total_rows=100,
            success_rows=50,
            failed_rows=50,
            field_mapping={"source_col": "target_col"},
            error_message=None,
            started_at=datetime.now(),
        )
        assert record.id == 1
        assert record.batch_no == "batch-123"
        assert record.data_source_id == 10
        assert record.file_name == "data.csv"
        assert record.file_type == FileType.CSV
        assert record.file_size == 2048
        assert record.status == ImportStatus.PROCESSING


class TestDataImportDetailModel:
    def test_default_values(self):
        detail = DataImportDetail(
            import_record_id=1,
            row_number=1,
        )
        assert detail.status == ImportStatus.PENDING
        assert detail.row_data is None
        assert detail.error_message is None

    def test_model_fields(self):
        detail = DataImportDetail(
            id=1,
            import_record_id=5,
            row_number=10,
            row_data={"col1": "val1", "col2": "val2"},
            status=ImportStatus.FAILED,
            error_message="Invalid date format",
        )
        assert detail.id == 1
        assert detail.import_record_id == 5
        assert detail.row_number == 10
        assert detail.row_data == {"col1": "val1", "col2": "val2"}
        assert detail.status == ImportStatus.FAILED


class TestDataImportRecordRepository:
    @pytest.mark.asyncio
    async def test_create_record(self, import_test_db):
        repo = DataImportRecordRepository(import_test_db)
        data = {
            "batch_no": "test-batch-001",
            "file_name": "test.xlsx",
            "file_type": FileType.EXCEL,
            "file_size": 1024,
            "file_path": "/uploads/test.xlsx",
        }
        record = await repo.create(data)
        assert record.id is not None
        assert record.batch_no == "test-batch-001"
        assert record.status == ImportStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_by_id(self, import_test_db):
        repo = DataImportRecordRepository(import_test_db)
        data = {
            "batch_no": "test-batch-002",
            "file_name": "test.csv",
            "file_type": FileType.CSV,
            "file_size": 2048,
            "file_path": "/uploads/test.csv",
        }
        created = await repo.create(data)
        record = await repo.get_by_id(created.id)
        assert record is not None
        assert record.batch_no == "test-batch-002"

    @pytest.mark.asyncio
    async def test_get_by_batch_no(self, import_test_db):
        repo = DataImportRecordRepository(import_test_db)
        data = {
            "batch_no": "unique-batch-123",
            "file_name": "data.xlsx",
            "file_type": FileType.EXCEL,
            "file_size": 512,
            "file_path": "/uploads/data.xlsx",
        }
        await repo.create(data)
        record = await repo.get_by_batch_no("unique-batch-123")
        assert record is not None
        assert record.file_name == "data.xlsx"

    @pytest.mark.asyncio
    async def test_update_status(self, import_test_db):
        repo = DataImportRecordRepository(import_test_db)
        data = {
            "batch_no": "update-test-001",
            "file_name": "update.xlsx",
            "file_type": FileType.EXCEL,
            "file_size": 100,
            "file_path": "/uploads/update.xlsx",
        }
        created = await repo.create(data)
        updated = await repo.update_status(created.id, ImportStatus.PROCESSING)
        assert updated.status == ImportStatus.PROCESSING

    @pytest.mark.asyncio
    async def test_update_counts(self, import_test_db):
        repo = DataImportRecordRepository(import_test_db)
        data = {
            "batch_no": "count-test-001",
            "file_name": "count.xlsx",
            "file_type": FileType.EXCEL,
            "file_size": 100,
            "file_path": "/uploads/count.xlsx",
        }
        created = await repo.create(data)
        updated = await repo.update_counts(
            created.id,
            total_rows=100,
            success_rows=80,
            failed_rows=20,
        )
        assert updated.total_rows == 100
        assert updated.success_rows == 80
        assert updated.failed_rows == 20

    @pytest.mark.asyncio
    async def test_mark_completed_success(self, import_test_db):
        repo = DataImportRecordRepository(import_test_db)
        data = {
            "batch_no": "complete-test-001",
            "file_name": "complete.xlsx",
            "file_type": FileType.EXCEL,
            "file_size": 100,
            "file_path": "/uploads/complete.xlsx",
        }
        created = await repo.create(data)
        updated = await repo.mark_completed(created.id, success_rows=100, failed_rows=0)
        assert updated.status == ImportStatus.SUCCESS
        assert updated.success_rows == 100
        assert updated.failed_rows == 0
        assert updated.completed_at is not None

    @pytest.mark.asyncio
    async def test_mark_completed_partial(self, import_test_db):
        repo = DataImportRecordRepository(import_test_db)
        data = {
            "batch_no": "partial-test-001",
            "file_name": "partial.xlsx",
            "file_type": FileType.EXCEL,
            "file_size": 100,
            "file_path": "/uploads/partial.xlsx",
        }
        created = await repo.create(data)
        updated = await repo.mark_completed(created.id, success_rows=90, failed_rows=10)
        assert updated.status == ImportStatus.PARTIAL
        assert updated.success_rows == 90
        assert updated.failed_rows == 10

    @pytest.mark.asyncio
    async def test_get_paginated(self, import_test_db):
        repo = DataImportRecordRepository(import_test_db)
        for i in range(5):
            await repo.create(
                {
                    "batch_no": f"paginated-batch-{i}",
                    "file_name": f"file{i}.xlsx",
                    "file_type": FileType.EXCEL,
                    "file_size": 100,
                    "file_path": f"/uploads/file{i}.xlsx",
                }
            )

        records, total = await repo.get_paginated(page=1, size=3)
        assert len(records) == 3
        assert total == 5

    @pytest.mark.asyncio
    async def test_get_paginated_with_filter(self, import_test_db):
        repo = DataImportRecordRepository(import_test_db)
        await repo.create(
            {
                "batch_no": "filter-pending",
                "file_name": "pending.xlsx",
                "file_type": FileType.EXCEL,
                "file_size": 100,
                "file_path": "/uploads/pending.xlsx",
                "status": ImportStatus.PENDING,
            }
        )
        await repo.create(
            {
                "batch_no": "filter-success",
                "file_name": "success.xlsx",
                "file_type": FileType.EXCEL,
                "file_size": 100,
                "file_path": "/uploads/success.xlsx",
                "status": ImportStatus.SUCCESS,
            }
        )

        records, total = await repo.get_paginated(
            page=1, size=10, status=ImportStatus.PENDING
        )
        assert len(records) == 1
        assert records[0].batch_no == "filter-pending"

    @pytest.mark.asyncio
    async def test_delete(self, import_test_db):
        repo = DataImportRecordRepository(import_test_db)
        data = {
            "batch_no": "delete-test-001",
            "file_name": "delete.xlsx",
            "file_type": FileType.EXCEL,
            "file_size": 100,
            "file_path": "/uploads/delete.xlsx",
        }
        created = await repo.create(data)
        record_id = created.id
        await repo.delete(record_id)
        deleted = await repo.get_by_id(record_id)
        assert deleted is None


class TestDataImportDetailRepository:
    @pytest.mark.asyncio
    async def test_create_detail(self, import_test_db):
        record_repo = DataImportRecordRepository(import_test_db)
        record_data = {
            "batch_no": "detail-batch-001",
            "file_name": "detail.xlsx",
            "file_type": FileType.EXCEL,
            "file_size": 100,
            "file_path": "/uploads/detail.xlsx",
        }
        record = await record_repo.create(record_data)

        detail_repo = DataImportDetailRepository(import_test_db)
        detail_data = {
            "import_record_id": record.id,
            "row_number": 1,
            "row_data": {"col": "value"},
        }
        detail = await detail_repo.create(detail_data)
        assert detail.id is not None
        assert detail.import_record_id == record.id
        assert detail.row_number == 1

    @pytest.mark.asyncio
    async def test_bulk_create(self, import_test_db):
        record_repo = DataImportRecordRepository(import_test_db)
        record = await record_repo.create(
            {
                "batch_no": "bulk-batch-001",
                "file_name": "bulk.xlsx",
                "file_type": FileType.EXCEL,
                "file_size": 100,
                "file_path": "/uploads/bulk.xlsx",
            }
        )

        detail_repo = DataImportDetailRepository(import_test_db)
        details_data = [
            {"import_record_id": record.id, "row_number": i, "row_data": {"row": i}}
            for i in range(10)
        ]
        details = await detail_repo.bulk_create(details_data)
        assert len(details) == 10

    @pytest.mark.asyncio
    async def test_get_by_import_record(self, import_test_db):
        record_repo = DataImportRecordRepository(import_test_db)
        record = await record_repo.create(
            {
                "batch_no": "get-by-record-001",
                "file_name": "record.xlsx",
                "file_type": FileType.EXCEL,
                "file_size": 100,
                "file_path": "/uploads/record.xlsx",
            }
        )

        detail_repo = DataImportDetailRepository(import_test_db)
        for i in range(3):
            await detail_repo.create(
                {
                    "import_record_id": record.id,
                    "row_number": i,
                }
            )

        details = await detail_repo.get_by_import_record(record.id)
        assert len(details) == 3

    @pytest.mark.asyncio
    async def test_get_failed_details(self, import_test_db):
        record_repo = DataImportRecordRepository(import_test_db)
        record = await record_repo.create(
            {
                "batch_no": "failed-batch-001",
                "file_name": "failed.xlsx",
                "file_type": FileType.EXCEL,
                "file_size": 100,
                "file_path": "/uploads/failed.xlsx",
            }
        )

        detail_repo = DataImportDetailRepository(import_test_db)
        await detail_repo.create(
            {
                "import_record_id": record.id,
                "row_number": 1,
                "status": ImportStatus.SUCCESS,
            }
        )
        await detail_repo.create(
            {
                "import_record_id": record.id,
                "row_number": 2,
                "status": ImportStatus.FAILED,
                "error_message": "Invalid data",
            }
        )
        await detail_repo.create(
            {
                "import_record_id": record.id,
                "row_number": 3,
                "status": ImportStatus.FAILED,
                "error_message": "Missing field",
            }
        )

        failed = await detail_repo.get_failed_by_import_record(record.id)
        assert len(failed) == 2
        assert all(d.status == ImportStatus.FAILED for d in failed)

    @pytest.mark.asyncio
    async def test_update_detail_status(self, import_test_db):
        record_repo = DataImportRecordRepository(import_test_db)
        record = await record_repo.create(
            {
                "batch_no": "update-detail-001",
                "file_name": "update.xlsx",
                "file_type": FileType.EXCEL,
                "file_size": 100,
                "file_path": "/uploads/update.xlsx",
            }
        )

        detail_repo = DataImportDetailRepository(import_test_db)
        detail = await detail_repo.create(
            {
                "import_record_id": record.id,
                "row_number": 1,
                "status": ImportStatus.PENDING,
            }
        )

        updated = await detail_repo.update_status(
            detail.id, ImportStatus.FAILED, "Test error"
        )
        assert updated.status == ImportStatus.FAILED
        assert updated.error_message == "Test error"


class TestCascadeDelete:
    @pytest.mark.asyncio
    async def test_delete_record_cascades_details(self, import_test_db):
        record_repo = DataImportRecordRepository(import_test_db)
        record = await record_repo.create(
            {
                "batch_no": "cascade-test-001",
                "file_name": "cascade.xlsx",
                "file_type": FileType.EXCEL,
                "file_size": 100,
                "file_path": "/uploads/cascade.xlsx",
            }
        )

        detail_repo = DataImportDetailRepository(import_test_db)
        for i in range(5):
            await detail_repo.create(
                {
                    "import_record_id": record.id,
                    "row_number": i,
                }
            )

        await record_repo.delete(record.id)

        details = await detail_repo.get_by_import_record(record.id)
        assert len(details) == 0
