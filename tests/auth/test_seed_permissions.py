from src.auth.seed import PERMISSIONS


def test_data_source_permissions_in_seed():
    codes = [p[0] for p in PERMISSIONS]
    assert "data_source:view" in codes
    assert "data_source:create" in codes
    assert "data_source:update" in codes
    assert "data_source:delete" in codes


def test_data_import_permissions_in_seed():
    codes = [p[0] for p in PERMISSIONS]
    assert "data_import:view" in codes
    assert "data_import:upload" in codes
    assert "data_import:parse" in codes
    assert "data_import:validate" in codes
    assert "data_import:confirm" in codes


def test_task_permissions_in_seed():
    codes = [p[0] for p in PERMISSIONS]
    assert "task:view" in codes
    assert "task:create" in codes
    assert "task:execute" in codes
    assert "task:cancel" in codes
