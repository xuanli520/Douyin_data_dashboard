import pytest
import json
from unittest.mock import AsyncMock


@pytest.fixture
def mock_cache():
    cache = AsyncMock()
    cache.set = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.delete = AsyncMock()
    return cache


@pytest.fixture
def progress_store(mock_cache):
    from src.domains.data_import.parser.progress_store import ParseProgressStore

    return ParseProgressStore(mock_cache)


@pytest.mark.asyncio
async def test_save_progress(progress_store, mock_cache):
    await progress_store.save_progress(
        file_id="file123",
        file_path="/uploads/test.csv",
        file_type="csv",
        current_row=100,
        total_rows=1000,
        file_hash="abc123",
    )

    mock_cache.set.assert_called_once()
    saved_data = json.loads(mock_cache.set.call_args[0][1])
    assert saved_data["file_id"] == "file123"
    assert saved_data["current_row"] == 100
    assert saved_data["total_rows"] == 1000


@pytest.mark.asyncio
async def test_get_progress_found(progress_store, mock_cache):
    stored_data = {
        "file_id": "file123",
        "file_path": "/uploads/test.csv",
        "file_type": "csv",
        "current_row": 100,
        "total_rows": 1000,
        "last_updated": "2024-01-01T00:00:00",
        "file_hash": "abc123",
    }
    mock_cache.get.return_value = json.dumps(stored_data)

    result = await progress_store.get_progress("file123")

    assert result is not None
    assert result.file_id == "file123"
    assert result.current_row == 100


@pytest.mark.asyncio
async def test_get_progress_not_found(progress_store, mock_cache):
    mock_cache.get.return_value = None

    result = await progress_store.get_progress("nonexistent")

    assert result is None


@pytest.mark.asyncio
async def test_delete_progress(progress_store, mock_cache):
    await progress_store.delete_progress("file123")

    mock_cache.delete.assert_called_once()
    key = mock_cache.delete.call_args[0][0]
    assert "file123" in key


@pytest.mark.asyncio
async def test_save_progress_with_ttl(progress_store, mock_cache):
    await progress_store.save_progress(
        file_id="file123",
        file_path="/uploads/test.csv",
        file_type="csv",
        current_row=100,
        total_rows=1000,
        file_hash="abc123",
        ttl=3600,
    )

    mock_cache.set.assert_called_once()
    ttl_used = mock_cache.set.call_args[0][2]
    assert ttl_used == 3600


@pytest.mark.asyncio
async def test_progress_key_format(progress_store):
    key = progress_store._key("test_file")
    assert key == "data_import:progress:test_file"


@pytest.mark.asyncio
async def test_save_progress_contains_all_fields(progress_store, mock_cache):
    await progress_store.save_progress(
        file_id="file456",
        file_path="/uploads/data.xlsx",
        file_type="xlsx",
        current_row=50,
        total_rows=500,
        file_hash="xyz789",
    )

    saved_data = json.loads(mock_cache.set.call_args[0][1])
    assert saved_data["file_path"] == "/uploads/data.xlsx"
    assert saved_data["file_type"] == "xlsx"
    assert saved_data["file_hash"] == "xyz789"
    assert "last_updated" in saved_data


@pytest.mark.asyncio
async def test_get_progress_returns_progressdata(progress_store, mock_cache):
    stored_data = {
        "file_id": "test_id",
        "file_path": "/path/to/file",
        "file_type": "csv",
        "current_row": 200,
        "total_rows": 2000,
        "last_updated": "2024-06-15T12:00:00",
        "file_hash": "hash123",
    }
    mock_cache.get.return_value = json.dumps(stored_data)

    result = await progress_store.get_progress("test_id")

    from src.domains.data_import.parser.progress_store import ProgressData

    assert isinstance(result, ProgressData)
    assert result.file_id == "test_id"
    assert result.current_row == 200
    assert result.total_rows == 2000


@pytest.mark.asyncio
async def test_progress_store_default_prefix(progress_store):
    assert progress_store._prefix == "data_import:progress:"
