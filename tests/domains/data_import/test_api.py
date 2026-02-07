import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from src.domains.data_import.enums import ImportStatus


class TestDataImportAPI:
    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = 1
        user.is_active = True
        return user

    @pytest.mark.asyncio
    async def test_upload_file_endpoint_exists(self):
        from src.api.v1.data_import import router

        route_paths = [r.path for r in router.routes]
        assert "/data-import/upload" in route_paths
        assert "/data-import/parse" in route_paths
        assert "/data-import/mapping" in route_paths
        assert "/data-import/validate" in route_paths
        assert "/data-import/confirm" in route_paths
        assert "/data-import/history" in route_paths
        assert "/data-import/{import_id}" in route_paths
        assert "/data-import/{import_id}/cancel" in route_paths

    @pytest.mark.asyncio
    async def test_parse_file_endpoint_structure(self):
        from src.api.v1.data_import import router

        assert hasattr(router, "post")
        route_paths = [r.path for r in router.routes]
        assert "/data-import/upload" in route_paths
        assert "/data-import/parse" in route_paths
        assert "/data-import/mapping" in route_paths
        assert "/data-import/validate" in route_paths
        assert "/data-import/confirm" in route_paths
        assert "/data-import/history" in route_paths
        assert "/data-import/{import_id}" in route_paths
        assert "/data-import/{import_id}/cancel" in route_paths


class TestDataImportSchemas:
    def test_import_upload_response_schema(self):
        from src.domains.data_import.schemas import ImportUploadResponse

        data = {
            "id": 1,
            "file_name": "test.csv",
            "file_size": 1024,
            "status": "PENDING",
            "created_at": datetime.now(timezone.utc),
        }
        response = ImportUploadResponse(**data)
        assert response.id == 1
        assert response.file_name == "test.csv"
        assert response.status == "PENDING"

    def test_import_parse_response_schema(self):
        from src.domains.data_import.schemas import ImportParseResponse

        data = {"id": 1, "total_rows": 100, "preview": [{"field": "value"}]}
        response = ImportParseResponse(**data)
        assert response.id == 1
        assert response.total_rows == 100
        assert len(response.preview) == 1

    def test_field_mapping_request_schema(self):
        from src.domains.data_import.schemas import FieldMappingRequest

        data = {
            "mappings": {"old_field": "new_field"},
            "target_fields": ["new_field", "another_field"],
        }
        request = FieldMappingRequest(**data)
        assert request.mappings == {"old_field": "new_field"}
        assert "new_field" in request.target_fields

    def test_import_validate_response_schema(self):
        from src.domains.data_import.schemas import ImportValidateResponse

        data = {
            "id": 1,
            "total_rows": 100,
            "passed": 95,
            "failed": 5,
            "errors_by_field": {"order_id": 3, "amount": 2},
            "warnings_by_field": {"date": 1},
        }
        response = ImportValidateResponse(**data)
        assert response.id == 1
        assert response.passed == 95
        assert response.failed == 5
        assert "order_id" in response.errors_by_field

    def test_import_confirm_response_schema(self):
        from src.domains.data_import.schemas import ImportConfirmResponse

        data = {
            "id": 1,
            "total": 100,
            "success": 98,
            "failed": 2,
            "errors": [{"row": 1, "error": "Invalid data"}],
        }
        response = ImportConfirmResponse(**data)
        assert response.success == 98
        assert response.failed == 2
        assert len(response.errors) == 1

    def test_import_history_response_schema(self):
        from src.domains.data_import.schemas import (
            ImportHistoryResponse,
            ImportHistoryItem,
        )

        items = [
            ImportHistoryItem(
                id=1,
                file_name="file1.csv",
                status="SUCCESS",
                total_rows=100,
                success_rows=100,
                failed_rows=0,
                created_at=datetime.now(timezone.utc),
            )
        ]
        response = ImportHistoryResponse(items=items, total=1, page=1, size=20, pages=1)
        assert len(response.items) == 1
        assert response.total == 1

    def test_import_detail_response_schema(self):
        from src.domains.data_import.schemas import ImportDetailResponse

        data = {
            "id": 1,
            "file_name": "test.csv",
            "file_path": "/uploads/test.csv",
            "file_size": 1024,
            "status": "SUCCESS",
            "field_mapping": {"old": "new"},
            "total_rows": 100,
            "success_rows": 98,
            "failed_rows": 2,
            "error_message": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        response = ImportDetailResponse(**data)
        assert response.file_name == "test.csv"
        assert response.field_mapping == {"old": "new"}

    def test_import_cancel_response_schema(self):
        from src.domains.data_import.schemas import ImportCancelResponse

        data = {
            "id": 1,
            "status": "CANCELLED",
            "message": "Import cancelled successfully",
        }
        response = ImportCancelResponse(**data)
        assert response.status == "CANCELLED"
        assert "cancelled" in response.message.lower()


class TestImportStatusEnum:
    def test_import_status_values(self):
        assert ImportStatus.PENDING == "PENDING"
        assert ImportStatus.PROCESSING == "PROCESSING"
        assert ImportStatus.SUCCESS == "SUCCESS"
        assert ImportStatus.FAILED == "FAILED"
        assert ImportStatus.PARTIAL == "PARTIAL"

    def test_import_status_is_string_enum(self):
        status = ImportStatus.PENDING
        assert isinstance(status, str)
        assert status.value == "PENDING"
