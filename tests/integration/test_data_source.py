"""Integration tests for data source API endpoints.

These tests will be enabled once API endpoints are implemented.
"""

import pytest

pytestmark = pytest.mark.skip(reason="API endpoints not yet implemented")


class TestDataSourceAPI:
    async def test_create_data_source(self, test_client):
        response = await test_client.post(
            "/api/v1/data-sources",
            json={
                "name": "Test Douyin Shop",
                "description": "Test data source",
                "source_type": "douyin_shop",
                "account_id": "test_account",
                "account_name": "Test Account",
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Test Douyin Shop"
        assert data["source_type"] == "douyin_shop"

    async def test_list_data_sources(self, test_client):
        response = await test_client.get("/api/v1/data-sources")
        assert response.status_code == 200
        data = response.json()["data"]
        assert isinstance(data, list)

    async def test_get_data_source_detail(self, test_client):
        create_response = await test_client.post(
            "/api/v1/data-sources",
            json={"name": "Test DS", "source_type": "douyin_shop"},
        )
        ds_id = create_response.json()["data"]["id"]

        response = await test_client.get(f"/api/v1/data-sources/{ds_id}")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == ds_id

    async def test_update_data_source(self, test_client):
        create_response = await test_client.post(
            "/api/v1/data-sources",
            json={"name": "Test DS", "source_type": "douyin_shop"},
        )
        ds_id = create_response.json()["data"]["id"]

        response = await test_client.put(
            f"/api/v1/data-sources/{ds_id}",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Updated Name"

    async def test_delete_data_source(self, test_client):
        create_response = await test_client.post(
            "/api/v1/data-sources",
            json={"name": "Test DS to Delete", "source_type": "douyin_shop"},
        )
        ds_id = create_response.json()["data"]["id"]

        response = await test_client.delete(f"/api/v1/data-sources/{ds_id}")
        assert response.status_code == 200

        get_response = await test_client.get(f"/api/v1/data-sources/{ds_id}")
        assert get_response.status_code == 404


class TestScrapingRuleAPI:
    async def test_create_scraping_rule(self, test_client):
        ds_response = await test_client.post(
            "/api/v1/data-sources",
            json={"name": "Test DS", "source_type": "douyin_shop"},
        )
        ds_id = ds_response.json()["data"]["id"]

        response = await test_client.post(
            "/api/v1/scraping-rules",
            json={
                "name": "Test Rule",
                "data_source_id": ds_id,
                "max_videos": 50,
                "auto_schedule": True,
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Test Rule"
        assert data["data_source_id"] == ds_id

    async def test_list_scraping_rules_by_data_source(self, test_client):
        ds_response = await test_client.post(
            "/api/v1/data-sources",
            json={"name": "Test DS", "source_type": "douyin_shop"},
        )
        ds_id = ds_response.json()["data"]["id"]

        response = await test_client.get(f"/api/v1/data-sources/{ds_id}/scraping-rules")
        assert response.status_code == 200
        assert isinstance(response.json()["data"], list)


class TestDataImportAPI:
    async def test_upload_file(self, test_client):
        response = await test_client.post(
            "/api/v1/data-import/upload",
            files={"file": ("test.csv", b"col1,col2\nval1,val2", "text/csv")},
        )
        assert response.status_code == 200
        assert "upload_id" in response.json()["data"]

    async def test_parse_file(self, test_client):
        response = await test_client.post(
            "/api/v1/data-import/parse",
            json={"upload_id": "test_upload_id", "file_type": "csv"},
        )
        assert response.status_code == 200

    async def test_validate_data(self, test_client):
        response = await test_client.post(
            "/api/v1/data-import/validate",
            json={"upload_id": "test_upload_id", "mapping": {"col1": "field1"}},
        )
        assert response.status_code == 200

    async def test_confirm_import(self, test_client):
        response = await test_client.post(
            "/api/v1/data-import/confirm",
            json={"upload_id": "test_upload_id"},
        )
        assert response.status_code == 200

    async def test_get_import_history(self, test_client):
        response = await test_client.get("/api/v1/data-import/history")
        assert response.status_code == 200
        assert isinstance(response.json()["data"], list)


class TestTaskAPI:
    async def test_list_tasks(self, test_client):
        response = await test_client.get("/api/v1/tasks")
        assert response.status_code == 200
        assert isinstance(response.json()["data"], list)

    async def test_create_task(self, test_client):
        response = await test_client.post(
            "/api/v1/tasks",
            json={
                "name": "Test Task",
                "task_type": "order_collection",
                "data_source_id": 1,
                "schedule": "0 */6 * * *",
            },
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Test Task"

    async def test_run_task(self, test_client):
        create_response = await test_client.post(
            "/api/v1/tasks",
            json={
                "name": "Test Task",
                "task_type": "order_collection",
                "data_source_id": 1,
            },
        )
        task_id = create_response.json()["data"]["id"]

        response = await test_client.post(f"/api/v1/tasks/{task_id}/run")
        assert response.status_code == 200
        assert "execution_id" in response.json()["data"]

    async def test_get_task_executions(self, test_client):
        create_response = await test_client.post(
            "/api/v1/tasks",
            json={
                "name": "Test Task",
                "task_type": "order_collection",
                "data_source_id": 1,
            },
        )
        task_id = create_response.json()["data"]["id"]

        response = await test_client.get(f"/api/v1/tasks/{task_id}/executions")
        assert response.status_code == 200
        assert isinstance(response.json()["data"], list)
