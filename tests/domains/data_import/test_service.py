import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.domains.data_import.service import ImportService
from src.domains.data_import.enums import ImportStatus
from src.domains.data_import.models import DataImportRecord
from src.domains.data_import.mapping import FieldMapper
from src.domains.data_import.validator import ValidationService


class TestImportServiceUnit:
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.set = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.exists = AsyncMock(return_value=False)
        return redis

    @pytest.fixture
    def import_service(self, mock_session, mock_redis):
        return ImportService(session=mock_session, redis=mock_redis)

    def test_import_service_initialization(self, import_service):
        assert import_service.IMPORT_PREFIX == "import:"
        assert import_service.PROGRESS_KEY == "progress"
        assert import_service.CANCEL_KEY == "cancel"

    def test_get_progress_key(self, import_service):
        key = import_service._get_progress_key(123)
        assert key == "import:123:progress"

    def test_get_cancel_key(self, import_service):
        key = import_service._get_cancel_key(456)
        assert key == "import:456:cancel"

    @pytest.mark.asyncio
    async def test_upload_file_creates_record(self, import_service, mock_session):
        with patch.object(
            import_service.repo, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_record = MagicMock(spec=DataImportRecord)
            mock_record.id = 1
            mock_record.file_name = "test.csv"
            mock_record.file_size = 1024
            mock_record.status = ImportStatus.PENDING
            mock_record.created_at = datetime.now(timezone.utc)
            mock_create.return_value = mock_record

            _ = await import_service.upload_file(
                file_path="/uploads/test.csv",
                file_name="test.csv",
                file_size=1024,
                file_type="csv",
                data_source_id=1,
                batch_no="IMP-ABC123",
                user_id=1,
            )

            mock_create.assert_called_once()
            call_args = mock_create.call_args[0][0]
            assert call_args["file_name"] == "test.csv"
            assert call_args["file_size"] == 1024
            assert call_args["data_source_id"] == 1
            assert call_args["batch_no"] == "IMP-ABC123"

    @pytest.mark.asyncio
    async def test_parse_file_not_found(self, import_service, mock_session):
        with patch.object(
            import_service.repo, "get_by_id", new_callable=AsyncMock, return_value=None
        ):
            with pytest.raises(ValueError, match="Import record not found"):
                await import_service.parse_file(999)

    @pytest.mark.asyncio
    async def test_apply_mapping_not_found(self, import_service, mock_session):
        with patch.object(
            import_service.repo, "get_by_id", new_callable=AsyncMock, return_value=None
        ):
            with pytest.raises(ValueError, match="Import record not found"):
                await import_service.apply_mapping(
                    import_id=999,
                    mappings={"old_field": "new_field"},
                    target_fields=["new_field"],
                )

    @pytest.mark.asyncio
    async def test_validate_data_not_found(self, import_service, mock_session):
        with patch.object(
            import_service.repo, "get_by_id", new_callable=AsyncMock, return_value=None
        ):
            with pytest.raises(ValueError, match="Import record not found"):
                await import_service.validate_data(999, [{"field": "value"}])

    @pytest.mark.asyncio
    async def test_confirm_import_not_found(self, import_service, mock_session):
        with patch.object(
            import_service.repo, "get_by_id", new_callable=AsyncMock, return_value=None
        ):
            with pytest.raises(ValueError, match="Import record not found"):
                await import_service.confirm_import(999, [{"field": "value"}])

    @pytest.mark.asyncio
    async def test_confirm_import_failed_status_raises_error(
        self, import_service, mock_session
    ):
        mock_record = MagicMock(spec=DataImportRecord)
        mock_record.status = ImportStatus.FAILED
        mock_record.field_mapping = None

        with patch.object(
            import_service.repo,
            "get_by_id",
            new_callable=AsyncMock,
            return_value=mock_record,
        ):
            with pytest.raises(ValueError, match="Import has failed"):
                await import_service.confirm_import(1, [{"field": "value"}])

    @pytest.mark.asyncio
    async def test_get_import_record(self, import_service, mock_session):
        mock_record = MagicMock(spec=DataImportRecord)
        mock_record.id = 1

        with patch.object(
            import_service.repo,
            "get_by_id",
            new_callable=AsyncMock,
            return_value=mock_record,
        ):
            result = await import_service.get_import_record(1)
            assert result.id == 1

    @pytest.mark.asyncio
    async def test_get_import_detail(self, import_service, mock_session):
        mock_record = MagicMock(spec=DataImportRecord)
        mock_record.id = 1

        with patch.object(
            import_service.repo,
            "get_by_id",
            new_callable=AsyncMock,
            return_value=mock_record,
        ):
            result = await import_service.get_import_detail(1)
            assert result.id == 1

    @pytest.mark.asyncio
    async def test_cancel_import(self, import_service, mock_session, mock_redis):
        with patch.object(import_service.repo, "update_status", new_callable=AsyncMock):
            await import_service.cancel_import(1)
            mock_redis.set.assert_called_once()
            mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_get_progress_from_redis(
        self, import_service, mock_session, mock_redis
    ):
        import json

        mock_redis.get = AsyncMock(
            return_value=json.dumps({"stage": "parsing", "total": 100, "processed": 50})
        )

        result = await import_service.get_progress(1)
        assert result is not None
        assert result["stage"] == "parsing"
        assert result["total"] == 100

    @pytest.mark.asyncio
    async def test_get_progress_returns_none_without_redis(
        self, import_service, mock_session
    ):
        import_service.redis = None

        result = await import_service.get_progress(1)
        assert result is None

    @pytest.mark.asyncio
    async def test_list_import_history(self, import_service, mock_session):
        mock_records = [
            MagicMock(
                id=1,
                file_name="file1.csv",
                status=ImportStatus.SUCCESS,
                total_rows=100,
                success_rows=100,
                failed_rows=0,
                created_at=datetime.now(timezone.utc),
            ),
            MagicMock(
                id=2,
                file_name="file2.csv",
                status=ImportStatus.PENDING,
                total_rows=0,
                success_rows=0,
                failed_rows=0,
                created_at=datetime.now(timezone.utc),
            ),
        ]

        with patch.object(
            import_service.repo,
            "get_paginated",
            new_callable=AsyncMock,
            return_value=(mock_records, 2),
        ):
            items, total = await import_service.list_import_history(
                user_id=1, page=1, size=20
            )
            assert len(items) == 2
            assert total == 2


class TestFieldMapperIntegration:
    def test_auto_map_integration(self):
        mapper = FieldMapper()
        mapper.set_target_fields(["order_id", "amount", "order_date", "quantity"])

        source_fields = ["order_no", "total_amount", "下单日期", "num"]
        mappings = mapper.auto_map(source_fields, required_fields=["order_id"])

        assert len(mappings) > 0
        mapping_dict = {m.source_field: m.target_field for m in mappings}
        assert "order_no" in mapping_dict

    def test_transform_data_integration(self):
        mapper = FieldMapper()
        mapper.set_target_fields(["order_id", "amount"])
        mapper.add_manual_mapping("ord_no", "order_id", transform_func="strip")
        mapper.add_manual_mapping("total", "amount", transform_func="float")

        row = {"ord_no": "  O123  ", "total": "150.50"}
        transformed = mapper.transform_data(row)

        assert transformed["order_id"] == "O123"
        assert transformed["amount"] == 150.50


class TestValidationServiceIntegration:
    def test_validate_orders_integration(self):
        rows = [
            {"order_id": "O001", "amount": 100.00, "order_date": "2024-01-15"},
            {"order_id": "O002", "amount": 200.50, "order_date": "2024-01-16"},
        ]

        results = ValidationService.validate("order", rows)

        assert len(results) == 2
        assert all(r.status.value == "pass" for r in results)

    def test_validate_products_integration(self):
        rows = [
            {"sku": "SKU001", "price": 99.99, "stock": 100, "name": "Product 1"},
            {"sku": "SKU002", "price": 149.99, "stock": 50, "name": "Product 2"},
        ]

        results = ValidationService.validate("product", rows)

        assert len(results) == 2
        assert all(r.status.value in ["pass", "skip"] for r in results)

    def test_validate_and_summarize_integration(self):
        rows = [
            {"order_id": "O001", "amount": 100.00, "order_date": "2024-01-15"},
            {"order_id": "", "amount": -50.00, "order_date": "invalid"},
        ]

        summary = ValidationService.validate_and_summarize("order", rows)

        assert "total_rows" in summary
        assert "passed" in summary
        assert "failed" in summary
        assert "errors_by_field" in summary
        assert summary["passed"] == 1
        assert summary["failed"] == 1
